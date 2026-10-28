"""Actual supervised browser companion and independently rejected mutations."""

from __future__ import annotations

import copy
import gzip
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


@pytest.mark.parametrize(
    "category,kind", [("initial", "texture"), ("initial", "buffer"), ("tiles", "texture")]
)
def test_missing_explicit_owned_deletion_is_rejected(pair, category, kind):
    report, host = copy.deepcopy(pair)
    gpu = report["browser"]["runs"]["cached"]["gpu"]
    resource = next(r for r in gpu["resources"] if r["category"] == category and r["kind"] == kind)
    gpu["events"] = [
        e for e in gpu["events"] if not (e["id"] == resource["id"] and e["op"] == "delete")
    ]
    # Keep the misleading aggregate success flags: the verifier replays events.
    assert verify.validate(report, host, environ={})


@pytest.mark.parametrize(
    "field,value",
    [
        ("noReferences", False),
        ("explicitDeletionBeforeContextLoss", False),
        ("noGLError", False),
        ("staleReplyEvents", 1),
        ("deletedBuffers", 0),
        ("tilePeakBytes", 8 * 512 * 512 * 4 + 1),
    ],
)
def test_owned_lifetime_mutations_fail(pair, field, value):
    report, host = copy.deepcopy(pair)
    report["browser"]["runs"]["normal"]["gpu"][field] = value
    assert verify.validate(report, host, environ={})


@pytest.mark.parametrize("mode", ["cached", "fetch-all", "normal"])
def test_relabelled_tile_resources_cannot_understate_native_inventory(mode):
    # Reuse authentic bounded bytes; this metadata mutation needs no browser.
    retained = ROOT / "spec/performance/colored-owned-resources-2026-10-24"
    report = json.loads(gzip.decompress((retained / "browser.json.gz").read_bytes()))
    host = gzip.decompress((retained / "host.json.gz").read_bytes())
    assert verify.validate(report, host, environ={}) == []
    run = report["browser"]["runs"][mode]
    gpu = run["gpu"]
    tiles = [r for r in gpu["resources"] if r["category"] == "tiles"]
    kept = min(tiles, key=lambda r: r["bytes"])
    for resource in tiles:
        if resource is not kept:
            resource["category"] = "chart"
    for category, counts in gpu["categories"].items():
        counts["created"] = counts["deleted"] = sum(
            r["category"] == category for r in gpu["resources"]
        )
    live = {}
    gpu["tilePeakBytes"] = 0
    for event in gpu["events"]:
        live[event["id"]] = 0 if event["op"] == "delete" else event["bytes"]
        gpu["tilePeakBytes"] = max(gpu["tilePeakBytes"], live.get(kept["id"], 0))
    assert 0 < gpu["tilePeakBytes"] < max(s["stats"]["allocatedTileBytes"] for s in run["samples"])
    # Category totals and allocation replay agree with each other; only the
    # independent native inventory exposes this understated tile classification.
    verify.owned_gpu(gpu)
    assert verify.validate(report, host, environ={}) == ["owned tile peak below native inventory"]


def test_reallocation_event_cannot_be_omitted_from_peak(pair):
    report, host = copy.deepcopy(pair)
    gpu = report["browser"]["runs"]["cached"]["gpu"]
    resource = next(r for r in gpu["resources"] if r["kind"] == "buffer")
    at = next(
        i for i, e in enumerate(gpu["events"]) if e["id"] == resource["id"] and e["op"] == "delete"
    )
    gpu["events"][at:at] = [
        {"id": resource["id"], "op": "storage", "bytes": 64 * 1024**2},
        {"id": resource["id"], "op": "storage", "bytes": resource["bytes"]},
    ]
    assert verify.validate(report, host, environ={})


@pytest.mark.parametrize(
    "mutation", ["frozen", "no-draw", "no-transition", "source", "blank", "settled", "adoption"]
)
def test_normal_cadence_mutations_fail(pair, mutation):
    report, host = copy.deepcopy(pair)
    sample = report["browser"]["runs"]["normal"]["samples"][25]
    if mutation == "frozen":
        sample["frames"][0]["clock"] = 1000
    elif mutation == "no-draw":
        sample["frames"] = []
    elif mutation == "no-transition":
        sample["transitionFrames"] = 0
    elif mutation == "source":
        sample["frames"][0]["drawn"][0]["sourceAlive"] = False
    elif mutation == "blank":
        sample["frames"][0]["ink"]["densityPixels"] = 0
    elif mutation == "settled":
        sample["settledPixelSha256"] = "0" * 64
    else:
        sample["adoption"]["at"] = sample["frames"][-1]["at"] + 1
    assert verify.validate(report, host, environ={})


def test_hardware_request_cannot_promote_software_observations(pair):
    report, host = copy.deepcopy(pair)
    assert verify.validate(report, host, environ={}, require_hardware=True)
    report["browser"]["requested_gl"] = "hardware"
    report["browser"]["preflight"]["requested_gl"] = "hardware"
    assert verify.validate(report, host, environ={}, require_hardware=True)


def test_hashed_historical_schema1_control_keeps_its_original_scope():
    import gzip

    root = ROOT / "spec/performance/density-spill-browser-2026-10-24/integration-control"
    raw = gzip.decompress((root / "host.json.gz").read_bytes())
    browser_bytes = gzip.decompress((root / "browser.json.gz").read_bytes())
    assert verify.sha(raw) == "3673f7423277138e86c9a4a324f8eabbbf8735f0a313f67220ca9e8340a1c77b"
    assert (
        verify.sha(browser_bytes)
        == "c9973ae1a61db81859119a97bedacd2fb59bf7648d5268e66c1698cedc708b00"
    )
    browser = json.loads(browser_bytes)
    assert verify.validate(browser, raw, environ={}) == []
    assert verify.validate(browser, raw, environ={}, require_hardware=True)


def test_hashed_historical_main_receipt_is_validated_without_new_exemptions():
    import gzip

    root = ROOT / "benchmarks/results/colored-spill-browser-2026-10-24/hosted-main"
    commit = "885908f2799803c1f9d8f6482d091adbf2c94d76"
    raw = gzip.decompress((root / f"density-e2e-colored-100m-{commit}.json.gz").read_bytes())
    browser_bytes = gzip.decompress(
        (root / f"density-e2e-colored-browser-100m-{commit}.json.gz").read_bytes()
    )
    assert verify.sha(raw) == "20194b01d6e5112e270ed0df7277e0fdbaca393b38452277a5fe53473c130c24"
    assert (
        verify.sha(browser_bytes)
        == "64572c562ffb487599e62994310d0ef5fb9d49952d1fe1d748100a12ef1f6492"
    )
    # Read-only replay of the retained run context, never exported to this
    # process environment or used to allocate/execute an authority workload.
    context = json.loads(raw)["authority_context"]
    assert (
        verify.validate(json.loads(browser_bytes), raw, expected_sha=commit, environ=context) == []
    )
