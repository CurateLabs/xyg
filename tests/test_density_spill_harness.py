"""Resource/authority guard and cancellation, without large allocations."""

from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
from benchmarks import _density_spill as spill
from benchmarks import bench_density_e2e as bench

ROOT = Path(__file__).resolve().parents[1]


def test_tile_fixture_does_not_override_product_point_admission(monkeypatch):
    import xyg
    from xyg import interaction, kernels

    monkeypatch.setattr(interaction, "PYRAMID_MIN_POINTS", 1)
    monkeypatch.setattr(interaction, "PYRAMID_BASE_DIM", 256)
    x = np.linspace(0, 1, 16384)
    fig = xyg.scatter_chart(xyg.scatter(x, x, color=x, density=True, pyramid_spill=True)).figure()
    trace = fig.traces[0]
    interaction._ensure_pyramid(trace)
    store = interaction._tile_store_of(trace)
    window = (0.1, 0.2, 0.1, 0.2)
    try:
        product, _ = fig.density_view(trace.id, *window, 512, 512, tile_cache=spill.control(None))
        assert product["traces"][0]["mode"] == "points"
        assert product["traces"][0]["binning"] == "canonical-points"

        def forbidden(*_args, **_kwargs):
            pytest.fail("tile fixture used product density_view")

        monkeypatch.setattr(type(fig), "density_view", forbidden)
        msg, frames = spill.tile_request(
            fig, store, window, authority=False, tile_cache=spill.control(None)
        )
        assert msg["traces"][0]["id"] == trace.id
        assert msg["traces"][0]["mode"] == "density"
        assert len(frames) == 1 and frames[0][:8] == b"XYDT\x01\0\0\0"
        assert trace.drill_mode  # the fixture never changes product LOD state
        with pytest.raises(ValueError, match="control"):
            spill.tile_request(fig, store, window, authority=False, tile_cache=b"invalid")
    finally:
        kernels.tile_store_free(store)
        trace._tile_store = None


@pytest.mark.parametrize("points_reply", [False, True])
def test_authority_forwards_product_reply_without_native_fallback(monkeypatch, points_reply):
    from xyg import kernels

    observed = []
    packet = b"XYDT\x01\0\0\0"
    result = (
        {"traces": [{"mode": "points"}]}
        if points_reply
        else {"traces": [{"mode": "density", "density": {"tile_frame": 0}}]},
        [b"points" if points_reply else packet],
    )

    def product(*args, **kwargs):
        observed.append((args, kwargs))
        return result

    def forbidden(*_args, **_kwargs):
        pytest.fail("authority fell back to native tile fixture")

    monkeypatch.setattr(kernels, "tile_store_paint", forbidden)
    fig = SimpleNamespace(traces=[SimpleNamespace(id=7)], density_view=product)
    window, control = (0.1, 0.2, 0.3, 0.4), spill.control(None)
    if points_reply:
        with pytest.raises(RuntimeError, match="product-density-view"):
            spill.tile_request(fig, 99, window, authority=True, tile_cache=control)
    else:
        assert spill.tile_request(fig, 99, window, authority=True, tile_cache=control) is not None
    assert observed == [((7, *window, 512, 512), {"tile_cache": control})]


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
    assert report["schema_version"] == 2
    assert report["request_path"] == "native-tile-painter-fixture"
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


def test_darwin_snapshot_counts_group_rss_names_and_excludes_zombies(monkeypatch):
    calls = []

    def snapshot(argv, **kwargs):
        calls.append((argv, kwargs))
        return subprocess.CompletedProcess(
            argv,
            0,
            "0 0 0 R kernel_task\n10 10 100 S /usr/bin/python\n11 10 200 S /Apps/Chromium Helper\n12 10 900 Z zombie\n13 13 700 S other\n",
            "",
        )

    monkeypatch.setattr(bench.sys, "platform", "darwin")
    monkeypatch.setattr(bench.subprocess, "run", snapshot)
    rss, members = bench._group_snapshot(10)
    assert rss == 300 * 1024 and set(members) == {10, 11}
    assert members[11]["name"] == "/Apps/Chromium Helper"
    assert calls[0][0] == ["/bin/ps", "-axo", "pid=,pgid=,rss=,stat=,comm="]
    assert calls[0][1]["timeout"] == 2 and calls[0][1]["check"] is True


@pytest.mark.parametrize(
    "output", ["", "bad snapshot", "10 10 -1 S python", "10 10 1 S python\n10 10 2 S duplicate"]
)
def test_darwin_invalid_snapshot_cannot_report_zero_success(monkeypatch, output):
    monkeypatch.setattr(
        bench.subprocess, "run", lambda argv, **kw: subprocess.CompletedProcess(argv, 0, output, "")
    )
    with pytest.raises(RuntimeError, match="observer failed"):
        bench._darwin_process_snapshot()


def test_darwin_timeout_and_missing_group_member_fail_preallocation(monkeypatch, tmp_path):
    def timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired("ps", 2)

    monkeypatch.setattr(bench.subprocess, "run", timeout)
    with pytest.raises(RuntimeError, match="observer failed"):
        bench._darwin_process_snapshot()
    monkeypatch.setattr(
        bench, "_group_snapshot", lambda pgid: (1024, {os.getpid() + 1: {"name": "other"}})
    )
    with pytest.raises(RuntimeError, match="own live group member"):
        bench._run_supervisor(None, tmp_path)
    assert not list(tmp_path.iterdir())  # No worker config, process or source.


def test_observer_failure_cannot_disable_process_group_kill(monkeypatch):
    calls = []
    monkeypatch.setattr(bench.os, "killpg", lambda pgid, sig: calls.append((pgid, sig)))
    monkeypatch.setattr(
        bench, "_process_group_rss", lambda pgid: (_ for _ in ()).throw(RuntimeError("ps failed"))
    )
    bench._terminate_group(12345)
    assert calls == [(12345, signal.SIGTERM), (12345, signal.SIGKILL)]


def test_failed_renderer_preflight_cannot_reach_source_allocation(monkeypatch, tmp_path):
    from scripts import density_spill_browser_smoke as smoke

    def failed(*args, **kwargs):
        raise ValueError("actual software renderer")

    def forbidden(*args, **kwargs):
        pytest.fail("renderer preflight failure reached canonical source generation")

    monkeypatch.setattr(smoke, "renderer_preflight", failed)
    monkeypatch.setattr(spill, "generate", forbidden)
    with pytest.raises(ValueError, match="software renderer"):
        spill.run_host(
            {
                "points": 16384,
                "chunk_points": 4096,
                "colored_browser_report": "browser.json",
                "chrome": "unused",
                "browser_socket_parent": str(tmp_path),
                "timeout": 30,
            },
            tmp_path,
            {},
        )


def test_missing_live_worker_membership_fails_and_terminates_bounded_group(monkeypatch, tmp_path):
    import argparse

    original = bench._group_snapshot

    def missing(pgid):
        rss, members = original(pgid)
        if pgid != os.getpgrp():
            members.pop(pgid, None)
        return rss, members

    monkeypatch.setattr(bench, "_group_snapshot", missing)
    args = argparse.Namespace(
        points=16384,
        authority=False,
        chunk_points=4096,
        chrome=None,
        workload="colored-spill",
        timeout=30,
        max_rss_gib=4,
        max_disk_gib=1,
        payload_ceiling_bytes=4 * 1024**2,
        output=tmp_path / "host.json",
        colored_browser_report=None,
    )
    report, failed = bench._run_supervisor(args, tmp_path)
    assert failed and "observer_failed" in report["failure"]
    assert report["cleanup"]["orphan_pids_after_reap"] == []
    assert report["cleanup"]["worker_exit_code"] != 0


def test_hardware_authority_guard_rejects_forged_workflow_identity_without_execution():
    # Guard-only dictionaries; no Actions environment is installed and no
    # workload is launched at authority scale.
    env = {
        "GITHUB_EVENT_NAME": "workflow_dispatch",
        "GITHUB_REPOSITORY": "CurateLabs/xyg",
        "GITHUB_WORKFLOW_REF": "CurateLabs/xyg/.github/workflows/ceiling-benchmark.yml@refs/heads/main",
        "GITHUB_SHA": "a" * 40,
        "GITHUB_WORKFLOW_SHA": "a" * 40,
    }
    spill.hardware_context_guard(env, authority=True, system="Darwin", machine="arm64")
    for key in env:
        invalid = {**env, key: "forged"}
        with pytest.raises(ValueError, match="workflow identity"):
            spill.hardware_context_guard(invalid, authority=True, system="Darwin", machine="arm64")
    with pytest.raises(ValueError, match="Darwin arm64"):
        spill.hardware_context_guard(env, authority=True, system="Linux", machine="x86_64")
