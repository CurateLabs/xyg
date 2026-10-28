"""Mutation-proof report contract, using an actual bounded native run."""

from __future__ import annotations

import copy
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from scripts import verify_density_spill_report as verify

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def colored_report(tmp_path_factory):
    output = tmp_path_factory.mktemp("colored-spill") / "report.json"
    env = dict(os.environ)
    env["PATH"] = str(Path.home() / ".cargo/bin") + os.pathsep + env["PATH"]
    result = subprocess.run(
        [
            sys.executable,
            "benchmarks/bench_density_e2e.py",
            "--workload",
            "colored-spill",
            "--points",
            "16384",
            "--chunk-points",
            "4096",
            "--timeout",
            "120",
            "--output",
            str(output),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=150,
        env=env,
    )
    report = json.loads(output.read_text())
    assert result.returncode == 0, report
    assert verify.validate(report, environ={}) == []
    return report


def test_real_colored_spill_report_has_valid_artifact_hashes(colored_report):
    assert verify.validate(colored_report, environ={}, artifact_root=ROOT) == []
    assert colored_report["scope"] == "host-kernel-only"
    assert colored_report["browser"]["status"] == "not-run"


@pytest.mark.parametrize(
    ("path", "replacement"),
    [
        (("schema_version",), 1),
        (("request_path",), "product-density-view"),
        (("report_kind",), "density-e2e"),
        (("status",), "failed"),
        (("scope",), "phase4-complete"),
        (("limits", "max_tree_rss_bytes"), 13 * 1024**3),
        (("limits", "max_disk_bytes"), 5 * 1024**3),
        (("limits", "timeout_seconds"), 3601),
        (("latency_policy", "pan_p95_ms"), 160),
        (("latency_policy", "each_zoom_ms"), 500),
        (("timing_scope",), "browser round trip"),
        (("source", "columns", "color", "sha256"), "not-a-hash"),
        (("source", "columns", "x", "bytes"), 1),
        (("source", "color_mode"), "constant"),
        (("source", "chunk_points"), 1000001),
        (("mapping_inventory", "after_samples", "x", "mapped"), False),
        (("mapping_inventory", "admission", "color", "pointer_equal"), False),
        (("native_build_inputs", 0, "index_bytes"), 100_000_000),
        (("decisions", "tile_budget_bytes"), 512 * 1024**2),
        (("decisions", "control_prewarm"), False),
        (("initial_payload", "mean_color"), False),
        (("initial_payload", "binning"), "pyramid-L2-tiles"),
        (("samples", 0, "flags"), 0),
        (("samples", 0, "stats", "spilled_bytes"), 0),
        (("samples", 0, "stats", "over_budget"), True),
        (("samples", 0, "stats", "budget_bytes"), 512 * 1024**2),
        (("samples", 0, "kernel_ms"), float("nan")),
        (("samples", 24, "previous_level"), 5),
        (("samples", 0, "window"), [0.0, 1.0, 0.0, 1.0]),
        (("samples", 0, "inventory", 0, "sha256"), "e" * 64),
        (("fetch_all", 0, "inventory", 0, "sha256"), "f" * 64),
        (("pan_p95_ms",), 100000),
        (("count_color_oracle", "max_count_error"), 1),
        (("count_color_oracle", "rgb_tolerance"), 255),
        (("count_color_oracle", "max_rgb_error"), 3),
        (("count_color_oracle", "rgba_sha256"), None),
        (("host_memory_report", "canonical_bytes"), 1),
        (("host_memory_report", "bin_color_bytes"), 16384),
        (("final_stats", "spilled_bytes"), 0),
        (("provenance", "native_sha256"), "bad"),
        (("provenance", "client_sha256"), "bad"),
        (("provenance", "source_sha256"), "0" * 64),
        (("provenance", "environment_sha256"), "0" * 64),
        (("browser", "status"), "ok"),
        (("cleanup", "spill_store_released"), False),
        (("cleanup", "spill_files_remaining"), ["xy-tiles-leaked.xyts"]),
        (("cleanup", "orphan_pids_after_reap"), [123]),
        (("process_tree", "peak_temp_bytes"), 5 * 1024**3),
        (("process_tree", "worker_peak_rss_bytes"), 13 * 1024**3),
    ],
)
def test_verifier_rejects_mutation(colored_report, path, replacement):
    report = copy.deepcopy(colored_report)
    value = report
    for part in path[:-1]:
        value = value[part]
    value[path[-1]] = replacement
    assert verify.validate(report, environ={}), path


@pytest.mark.parametrize("sample_field", ["samples", "fetch_all"])
def test_missing_raw_sample_rejected(colored_report, sample_field):
    report = copy.deepcopy(colored_report)
    report[sample_field].pop()
    assert "raw samples missing" in verify.validate(report, environ={})[0]


@pytest.mark.parametrize("kind", ["native", "client"])
def test_valid_but_wrong_artifact_digest_rejected(colored_report, kind):
    report = copy.deepcopy(colored_report)
    report["provenance"][kind + "_sha256"] = "a" * 64
    assert "hash mismatch" in verify.validate(report, environ={}, artifact_root=ROOT)[0]


def test_authority_cannot_be_spoofed_by_report_fields(colored_report):
    report = copy.deepcopy(colored_report)
    report.update(authority=True, point_count=100_000_000)
    sha = report["environment"]["git"]["commit"]
    report["authority_context"] = {
        "GITHUB_ACTIONS": "true",
        "GITHUB_REF": "refs/heads/main",
        "GITHUB_EVENT_NAME": "schedule",
        "GITHUB_RUN_ID": "1234",
        "GITHUB_RUN_ATTEMPT": "1",
        "GITHUB_SHA": sha,
        "XYG_DENSITY_100M_AUTHORITY": "1",
    }
    assert "ambient" in verify.validate(report, environ={}, expected_sha=sha)[0]
    assert "--sha" in verify.validate(report, environ={})[0]


def test_missing_request_path_is_not_accepted_as_legacy(colored_report):
    report = copy.deepcopy(colored_report)
    del report["request_path"]
    assert verify.validate(report, environ={})


def test_control_latency_is_advisory_but_budget_is_not_editable(colored_report):
    report = copy.deepcopy(colored_report)
    for sample in report["samples"]:
        sample["kernel_ms"] = 100.0
    report.update(pan_p95_ms=100.0, zoom_max_ms=100.0)
    assert verify.validate(report, environ={}) == []
    report["latency_policy"]["each_zoom_ms"] = 101
    assert verify.validate(report, environ={})


@pytest.mark.parametrize("value", [None, [], {}, {"schema_version": True}, "ok", 123])
def test_malformed_reports_fail_closed(value):
    assert verify.validate(value, environ={})


@pytest.mark.parametrize(
    ("pans", "zooms"),
    [
        ([16.0] * 24, [1.0] * 8),
        ([1.0] * 24, [1.0] * 7 + [50.0]),
        ([1.0] * 19, [1.0] * 8),
        ([1.0] * 24, [1.0] * 7),
    ],
)
def test_authority_has_independent_strict_latency_limits(pans, zooms):
    with pytest.raises(verify.InvalidReport):
        verify.check_latency(pans, zooms, True)


def test_authority_checks_every_zoom_and_control_remains_advisory():
    assert verify.check_latency([15.0] * 24, [49.0] * 8, True) == (15.0, 49.0)
    assert verify.check_latency([100.0] * 24, [100.0] * 8, False) == (100.0, 100.0)
