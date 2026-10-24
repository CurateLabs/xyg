"""Actual supervised browser companion and independently rejected mutations."""

from __future__ import annotations

import copy
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import pytest
from benchmarks import _density_spill as spill
from benchmarks import bench_density_e2e as bench
from scripts import verify_density_spill_browser_report as verify

ROOT = Path(__file__).resolve().parents[1]


def command(root, chrome, *, timeout="180"):
    return [
        sys.executable,
        "benchmarks/bench_density_e2e.py",
        "--workload",
        "colored-spill",
        "--points",
        "16384",
        "--chunk-points",
        "4096",
        "--timeout",
        timeout,
        "--max-rss-gib",
        "8",
        "--max-disk-gib",
        "2",
        "--chrome",
        chrome,
        "--temp-root",
        str(root),
        "--output",
        str(root / "host.json"),
        "--colored-browser-report",
        str(root / "browser.json"),
    ]


@pytest.fixture(scope="module")
def chrome():
    value = os.environ.get("XYG_TEST_CHROMIUM")
    if not value:
        pytest.skip("set XYG_TEST_CHROMIUM to an explicit Chrome/Chromium executable")
    assert Path(value).is_file()
    return value


@pytest.fixture(scope="module")
def pair(chrome, tmp_path_factory):
    root = tmp_path_factory.mktemp("browser-companion")
    result = subprocess.run(
        command(root, chrome), cwd=ROOT, capture_output=True, text=True, timeout=210
    )
    browser = json.loads((root / "browser.json").read_bytes())
    host = (root / "host.json").read_bytes()
    assert result.returncode == 0, (result.stderr, browser)
    assert verify.validate(browser, host, environ={}, artifact_root=ROOT) == []
    return browser, host


def test_actual_supervised_browser_keeps_host_scope(pair):
    browser, host_bytes = pair
    host = json.loads(host_bytes)
    assert host["scope"] == "host-kernel-only" and host["browser"]["status"] == "not-run"
    assert "_browser_companion" not in host
    assert browser["source"] == host["source"]
    assert browser["host_report_sha256"] == verify.sha(host_bytes)
    assert browser["process_tree"]["browser_process_observed"]
    assert verify.validate(browser, host_bytes + b"\n", environ={})  # exact bytes, not parsed JSON


@pytest.mark.parametrize(
    ("path", "replacement"),
    [
        (("status",), "failed"),
        (("scope",), "FPS"),
        (("report_kind",), "density-e2e"),
        (("host_report_sha256",), "0" * 64),
        (("point_count",), 100_000_000),
        (("authority",), True),
        (("authority_context", "GITHUB_REF"), "refs/heads/main"),
        (("source", "columns", "color", "sha256"), "0" * 64),
        (("source", "bytes"), 24),
        (("domain", 0), -1),
        (("windows", 31, "window", 0), -1),
        (("windows",), []),
        (("provenance", "client_sha256"), "0" * 64),
        (("provenance", "native_sha256"), "0" * 64),
        (("limits", "max_tree_rss_bytes"), 13 * 1024**3),
        (("limits", "max_disk_bytes"), 5 * 1024**3),
        (("limits", "timeout_seconds"), 3601),
        (("process_tree", "browser_process_observed"), False),
        (("host_cleanup", "temp_tree_removed"), False),
        (("host_cleanup", "browser_socket_alias_removed"), False),
        (("cleanup", "server_stopped"), False),
        (("browser_artifacts", "harness_sha256"), "bad"),
        (("browser", "pid"), 1),
        (("browser", "pgid"), 1),
        (("browser", "process_reaped"), False),
        (("browser", "profile_removed"), False),
        (("mapping_inventory", "after_browser", "x", "pointer_equal"), False),
        (("initial_payload", "blob_bytes"), 1),
        (("initial_payload", "blob_sha256"), "bad"),
        (("bootstrap", "flags"), 5),
        (("requests", 1, "control_base64"), "AAAA"),
        (("requests", 25, "inventory", 0, "sha256"), "0" * 64),
        (("requests", 0, "flags"), 3),
        (("requests", 1, "stats", "over_budget"), True),
        (("browser", "runs", "cached", "gpu", "remainingTextures"), 1),
        (("browser", "runs", "cached", "gpu", "deletedTextures"), 0),
        (("browser", "runs", "cached", "gpu", "peakInstrumentedBytes"), 1024**3),
        (("browser", "runs", "cached", "destroyed"), False),
        (("browser", "runs", "fetch-all", "lateReplyIgnored"), False),
        (("browser", "runs", "cached", "samples", 0, "densityPixels"), 0),
        (("browser", "runs", "cached", "samples", 0, "bluePixels"), 0),
        (("browser", "runs", "cached", "samples", 0, "seam", "maxError"), 3),
        (("browser", "runs", "cached", "samples", 0, "seam", "tolerance"), 255),
        (("browser", "runs", "cached", "samples", 0, "seam", "overlappingCells"), 0),
        (("browser", "runs", "cached", "samples", 0, "seam", "densityPixels"), 0),
        (("browser", "runs", "cached", "samples", 0, "stats", "allocatedTileBytes"), 0),
        (("browser", "runs", "fetch-all", "samples", 32, "pixelSha256"), "0" * 64),
        (("browser", "runs", "fetch-all", "samples", 0, "cachedPixelEquality"), False),
        (("browser", "runs", "cached", "samples", 25, "fade", "sourceSurvived"), False),
        (("browser", "runs", "cached", "samples", 25, "fade", "sourceKeys"), []),
        (("browser", "runs", "cached", "samples", 25, "fade", "sourceLevel"), 5),
        (("browser", "runs", "cached", "samples", 25, "fade", "retired"), False),
        (("browser", "runs", "cached", "samples", 25, "fade", "drawn"), []),
        (("browser", "runs", "cached", "samples", 25, "fade", "startMid", "changedBytes"), 0),
        (("browser", "captures", "pan.png"), "data:image/png;base64,AAAA"),
    ],
)
def test_mutations_are_rejected(pair, path, replacement):
    browser, host = pair
    value = report = copy.deepcopy(browser)
    for part in path[:-1]:
        value = value[part]
    value[path[-1]] = replacement
    assert verify.validate(report, host, environ={}), path


def test_browser_artifact_content_is_verified(pair):
    browser, host = pair
    report = copy.deepcopy(browser)
    report["browser_artifacts"]["harness_sha256"] = "0" * 64
    assert verify.validate(report, host, environ={}, artifact_root=ROOT)


def test_untrusted_host_cannot_self_authorize(pair):
    browser, raw = pair
    host = json.loads(raw)
    host["authority"] = True
    host["point_count"] = 100_000_000
    report = copy.deepcopy(browser)
    altered = json.dumps(host).encode()
    report["host_report_sha256"] = verify.sha(altered)
    assert (
        "ambient"
        in verify.validate(
            report, altered, expected_sha=host["environment"]["git"]["commit"], environ={}
        )[0]
    )


@pytest.mark.parametrize(
    "options",
    [
        ["--points", "100000000"],
        ["--chrome", "/does/not/exist"],
        ["--workload", "resident-count"],
        ["--colored-browser-report", "SAME"],
    ],
)
def test_invalid_companion_guard_precedes_allocation(options, tmp_path, monkeypatch):
    def forbidden(*_args):
        pytest.fail("invalid companion reached worker/source allocation")

    monkeypatch.setattr(bench, "_run_supervisor", forbidden)
    # Use sys.executable: executable but does not identify Chrome. Same-output
    # validation is also tested directly below with real Chrome.
    args = command(tmp_path, sys.executable)[2:] + options
    monkeypatch.setattr(sys, "argv", ["bench_density_e2e.py", *args])
    with pytest.raises(SystemExit):
        bench.main()
    assert not list(tmp_path.glob("xyg-density-e2e-*"))


def test_output_guard_and_worker_entry(chrome, tmp_path):
    config = {
        "colored_browser_report": str(tmp_path / "host.json"),
        "host_output": str(tmp_path / "host.json"),
        "chrome": chrome,
        "workload": "colored-spill",
    }
    with pytest.raises(ValueError, match="distinct"):
        spill.browser_guard(config)
    config.update(
        points=16384,
        authority=False,
        timeout=180,
        max_rss_bytes=8 * 1024**3,
        max_disk_bytes=2 * 1024**3,
    )
    with pytest.raises(ValueError, match="distinct"):
        spill.worker(config)  # no tmp/runtime or mappings created
    assert not list(tmp_path.iterdir())


def test_timeout_fails_both_outputs_and_cleans_alias(chrome, tmp_path):
    aliases = set(Path.home().glob(".xyb-*"))
    result = subprocess.run(
        command(tmp_path, chrome, timeout=".001"), cwd=ROOT, capture_output=True, timeout=30
    )
    report = json.loads((tmp_path / "browser.json").read_bytes())
    host = json.loads((tmp_path / "host.json").read_bytes())
    assert result.returncode == 1 and report["status"] == host["status"] == "failed"
    assert host["failure"] == "timeout" and host["cleanup"]["orphan_pids_after_reap"] == []
    assert host["cleanup"]["temp_tree_removed"] and host["cleanup"]["browser_socket_alias_removed"]
    assert set(Path.home().glob(".xyb-*")) == aliases


def test_cancel_during_browser_reaps_whole_process_group(chrome, tmp_path):
    proc = subprocess.Popen(
        command(tmp_path, chrome), cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.PIPE
    )
    try:
        deadline = time.monotonic() + 40
        while time.monotonic() < deadline:
            configs = list(tmp_path.glob("xyg-density-e2e-*/config.json"))
            children = Path(f"/proc/{proc.pid}/task/{proc.pid}/children").read_text().split()
            if configs and children:
                _, pids = bench._process_group_rss(int(children[-1]))
                if any("chrome" in (bench._process_name(pid) or "") for pid in pids):
                    break
            assert proc.poll() is None
            time.sleep(0.05)
        else:
            pytest.fail("browser was not observed before cancellation")
        os.kill(proc.pid, signal.SIGTERM)
        proc.communicate(timeout=25)
        host = json.loads((tmp_path / "host.json").read_bytes())
        browser = json.loads((tmp_path / "browser.json").read_bytes())
        assert (
            proc.returncode == 1
            and host["failure"] == "cancelled"
            and browser["status"] == "failed"
        )
        assert (
            host["cleanup"]["orphan_pids_after_reap"] == [] and host["cleanup"]["temp_tree_removed"]
        )
        assert host["cleanup"]["browser_socket_alias_removed"]
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.communicate(timeout=10)


def test_browser_launch_failure_fails_invocation_and_cleans(tmp_path):
    chrome = tmp_path / "broken-chrome"
    chrome.write_text(
        '#!/bin/sh\nif [ "$1" = "--version" ]; then echo "Chromium 156"; exit 0; fi\nexit 7\n'
    )
    chrome.chmod(0o700)
    result = subprocess.run(
        command(tmp_path, str(chrome)), cwd=ROOT, capture_output=True, timeout=40
    )
    host = json.loads((tmp_path / "host.json").read_bytes())
    browser = json.loads((tmp_path / "browser.json").read_bytes())
    assert result.returncode == 1 and browser["status"] == host["status"] == "failed"
    assert "Chromium exited" in host["failure"]
    assert all(
        host["cleanup"][k]
        for k in (
            "figure_released",
            "spill_store_released",
            "mmap_closed",
            "temp_tree_removed",
            "browser_socket_alias_removed",
        )
    )
    assert host["cleanup"]["orphan_pids_after_reap"] == []


def test_companion_validation_failure_is_fatal(pair, chrome, tmp_path, monkeypatch):
    browser, host_bytes = pair
    host = json.loads(host_bytes)

    def completed_worker(*_args):
        report = copy.deepcopy(host)
        report["_browser_companion"] = copy.deepcopy(browser)
        return report, False

    monkeypatch.setattr(bench, "_run_supervisor", completed_worker)
    monkeypatch.setattr(
        verify, "validate", lambda *_args, **_kwargs: ["deliberate negative oracle"]
    )
    monkeypatch.setattr(sys, "argv", command(tmp_path, chrome)[1:])
    assert bench.main() == 1
    result = json.loads((tmp_path / "browser.json").read_bytes())
    assert result["status"] == "failed" and "negative oracle" in result["failure"]
    assert json.loads((tmp_path / "host.json").read_bytes())["browser"]["status"] == "not-run"
