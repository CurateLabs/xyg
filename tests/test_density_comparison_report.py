"""Mutation proofs over actual retained browser evidence; no browser or source allocation."""

from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/verify_density_comparison_report.py"
spec = importlib.util.spec_from_file_location("density_report_verifier", SCRIPT)
assert spec and spec.loader
v = importlib.util.module_from_spec(spec)
spec.loader.exec_module(v)
ARCHIVE = ROOT / v.ARCHIVE


@pytest.fixture
def report():
    r, _ = v.load_report(ARCHIVE / "f64-memmap.json.gz")
    # Small real subset, all three arms and both repetitions retained.
    r["sizes"] = [1000]
    r["authority"] = r["authority"][:1]
    r["sources"] = {"1000": r["sources"]["1000"]}
    r["results"] = [c for c in r["results"] if c["n"] == 1000]
    # Derived reports exercise the current contract; immutable archives above
    # retain their exact historical binding and bytes.
    r["environment"].update(
        browser_renderer="software-gl",
        browser_renderer_requested="software-gl",
        browser_renderer_observed=None,
        browser_renderer_scope="launch-request; actual renderer not measured",
    )
    # Synthetic current-contract metadata on retained pixels, for structural
    # mutations only. These hashes are fixture values, never measured evidence.
    r["numerical_contract"] = "source-cell-compose-v1"
    r["provenance_sha256"]["benchmarks/_ux_comparison_oracle.py"] = hashlib.sha256(
        (ROOT / "benchmarks/_ux_comparison_oracle.py").read_bytes()
    ).hexdigest()
    s = r["sources"]["1000"]
    s["source_bounds"] = list(s["extents"])
    for w in s["windows"]:
        w["source_counts"] = {
            "inclusive": w["expected_count"],
            "half_open": w["expected_count"],
            "upper_boundary_excluded": 0,
        }
    for c in r["results"]:
        c["host_meta"]["source"] = {
            k: copy.deepcopy(value)
            for k, value in s.items()
            if k not in ("creation_wall_ms", "source_peak_rss_bytes")
        }
        if c["arm"] != "xy-density":
            continue
        cold = c["cold"]["state"]
        cold["output"] = copy.deepcopy(c["steps"][0]["state"]["output"])
        cold["output"].update(
            revision=0,
            rendered_revision=0,
            domain=s["extents"],
            reply_domain=s["extents"],
            visible=1000,
        )
        for name, paint in [
            ("visible-complete", c["cold"]),
            *[(f"step-{i}", p) for i, p in enumerate(c["steps"])],
            ("empty-control", c["empty_control"]),
        ]:
            out = paint["state"]["output"]
            out.update(
                tier="density",
                encoding="log-u8",
                reply_max=out["reply_norm_max"],
                adopted_max=out["reply_norm_max"],
            )
            proof = {
                "version": "source-cell-compose-v1",
                "passed": True,
                "domain": out["domain"],
                "exact_source_count": paint["expected_count"],
                "half_open_source_count": paint["expected_count"],
                "upper_boundary_excluded": 0,
                "emitted_visible": out["visible"],
                "expected_visible": out["visible"],
                "count_method": "half-open-source",
                "count_exact": True,
                "boundary_mass_bound": 0,
                "base_geometry": None,
                "served_level": None,
                "raster_shape": out["raster_shape"],
                "expected_encoded_sha256": "1" * 64,
                "actual_encoded_sha256": "1" * 64,
                "expected_decoded_sha256": "2" * 64,
                "adopted_decoded_sha256": "2" * 64,
                "grid_sha256": "3" * 64,
                "encoded_bytes": out["raster_shape"][0] * out["raster_shape"][1],
                "expected_max": out["reply_max"],
                "actual_max": out["reply_max"],
                "grid_mass_diagnostic": paint["expected_count"],
                "source_sha256": s["sha256_x_then_y"],
                "points_allowed": False,
                "validation_wall_ms": 1,
                "validation_http_request_bytes": 100,
            }
            out["numerical_oracle"] = proof
            cp = c["transport"]["checkpoints"][name]
            cp["host_observation"]["numerical_oracle"] = copy.deepcopy(proof)
            cp["host_observation"]["numerical_oracle_preparation"] = {
                "version": "source-cell-compose-v1",
                "wall_ms": 1,
                "chunk_rows": 65536,
                "grid_storage_upper_bound_bytes": 1024,
                "scope": "host_prepare before META; host process-tree RSS/watchdog includes oracle",
            }
            if "host_observation" in paint:
                paint["host_observation"] = copy.deepcopy(cp["host_observation"])
    return r


def check(r, **kwargs):
    return v.validate(r, environ={}, host=("Linux", "x86_64"), **kwargs)


@pytest.mark.parametrize(
    "name,successes,failures",
    [
        ("f32.json.gz", 16, 2),
        ("f32-xy-cache-followup.json.gz", 2, 0),
        ("f64-memmap.json.gz", 18, 0),
    ],
)
def test_retained_raw_archives_bind_to_their_producers(name, successes, failures):
    r, historical = v.load_report(ARCHIVE / name)
    assert historical
    assert check(r, artifact_root=ROOT, historical=historical) == []
    assert sum(c["status"] == "ok" for c in r["results"]) == successes
    assert sum(c["status"] != "ok" for c in r["results"]) == failures


def test_structural_fixture_without_verifier_optional_dependencies(report):
    assert check(report, expected_sizes=[1000], expected_arms=list(v.ARMS)) == []
    assert "numpy" not in v.__dict__
    assert "psutil" not in v.__dict__


@pytest.mark.parametrize(
    "field,value",
    [
        ("passed", False),
        ("count_exact", False),
        ("expected_visible", 0),
        ("actual_encoded_sha256", "4" * 64),
        ("adopted_decoded_sha256", "4" * 64),
        ("source_sha256", "4" * 64),
        ("upper_boundary_excluded", 1),
        ("actual_max", -1),
    ],
)
def test_current_numerical_contract_rejects_mutations_even_if_host_agrees(report, field, value):
    c = report["results"][0]
    proof = c["steps"][0]["state"]["output"]["numerical_oracle"]
    proof[field] = value
    cp = c["transport"]["checkpoints"]["step-0"]["host_observation"]
    cp["numerical_oracle"] = copy.deepcopy(proof)
    c["steps"][0]["host_observation"] = copy.deepcopy(cp)
    assert check(report)


def test_current_report_cannot_omit_oracle_or_claim_historical_flag(report):
    del report["results"][0]["steps"][0]["state"]["output"]["numerical_oracle"]
    report["historical_archive_commit"] = (
        "21965ee46178049d37001c9028e80b72259cb1109b19593920560a3e697e06ce"
    )
    assert check(report)


def test_oracle_preparation_stays_inside_host_phase_and_provenance(report):
    c = report["results"][0]
    c["transport"]["checkpoints"]["visible-complete"]["host_observation"][
        "numerical_oracle_preparation"
    ]["wall_ms"] = c["host_prepare_wall_ms"] + 1
    assert check(report)
    c["transport"]["checkpoints"]["visible-complete"]["host_observation"][
        "numerical_oracle_preparation"
    ]["wall_ms"] = 1
    assert check(report) == []
    del report["provenance_sha256"]["benchmarks/_ux_comparison_oracle.py"]
    assert check(report) == ["missing independent oracle provenance"]


@pytest.mark.parametrize("failure", ["timeout", "exit", "source_mismatch"])
def test_real_silent_host_failures_remain_valid_evidence(report, monkeypatch, tmp_path, failure):
    pytest.importorskip("websocket")
    from types import SimpleNamespace

    from benchmarks import bench_density_comparison as runner

    manifest = tmp_path / "source.json"
    manifest.write_text(json.dumps(report["results"][0]["host_meta"]["source"]))
    real_popen = subprocess.Popen
    hosts = []
    command = {
        "timeout": "import time; time.sleep(30)",
        "exit": "pass",
        "source_mismatch": "print('META {\"source\": {}}', flush=True)",
    }[failure]

    def launch_host(_argv, **kwargs):
        child = real_popen([sys.executable, "-c", command], **kwargs)
        hosts.append(child)
        return child

    monkeypatch.setattr(runner.subprocess, "Popen", launch_host)
    row = runner.run_arm(
        "xy-density",
        manifest,
        SimpleNamespace(timeout=0.1 if failure == "timeout" else 5, memory_gib=2),
        0,
    )
    assert row["status"] == {"exit": "host_failed"}.get(failure, failure)
    assert row["reason"]
    assert row["host_stderr"] == ""
    assert all(child.poll() is not None for child in hosts)
    report["results"][0] = row
    assert check(report) == []


@pytest.mark.parametrize("hardware", [False, True])
def test_renderer_request_is_distinct_from_unmeasured_actual_renderer(report, hardware):
    # The producer is exercised separately; independent validation rejects aliases
    # or invented observations even if an inherited env label was the opposite.
    requested = "hardware" if hardware else "software-gl"
    if hardware:
        report["argv"].append("--hardware")
    report["environment"].update(
        browser_renderer=requested,
        browser_renderer_requested=requested,
        browser_renderer_observed=None,
        browser_renderer_scope="launch-request; actual renderer not measured",
    )
    assert check(report) == []
    report["environment"]["browser_renderer"] = (
        "hardware" if requested == "software-gl" else "software-gl"
    )
    assert check(report)
    report["environment"]["browser_renderer"] = requested
    report["environment"]["browser_renderer_observed"] = "unverified GPU"
    assert check(report)


@pytest.mark.parametrize(
    "key",
    [
        "browser_renderer",
        "browser_renderer_requested",
        "browser_renderer_observed",
        "browser_renderer_scope",
    ],
)
def test_new_renderer_fields_cannot_be_removed_to_bypass_validation(report, key):
    del report["environment"][key]
    assert check(report)


@pytest.mark.parametrize(
    "field,value",
    [
        ("schema_version", 2),
        ("experiment", "wheel"),
        ("plot_css_px", [513, 512]),
        ("repetitions", 1),
        ("repetitions", 4),
        ("repetitions", True),
        ("sizes", [1000, 1000]),
        ("sizes", [1_000_000_001]),
        ("arms", ["xy-density", "xy-density"]),
    ],
)
def test_top_level_contract_mutations(report, field, value):
    report[field] = value
    assert check(report)


def test_external_expected_scope_detects_dropped_targets(report):
    assert check(report, expected_sizes=[1000, 100_000_000])
    assert check(report, expected_arms=["xy-density"])
    report["arms"].remove("plotly-aggregate")
    report["results"] = [c for c in report["results"] if c["arm"] != "plotly-aggregate"]
    assert check(report) == []
    assert check(report, expected_arms=list(v.ARMS))


@pytest.mark.parametrize(
    "operation", ["drop", "duplicate", "repetition", "unknown_status", "missing_status"]
)
def test_all_cells_and_repetitions_required(report, operation):
    if operation == "drop":
        report["results"].pop()
    elif operation == "duplicate":
        report["results"][-1] = copy.deepcopy(report["results"][0])
    elif operation == "repetition":
        report["results"][0]["repetition"] = 2
    elif operation == "unknown_status":
        report["results"][0]["status"] = "pretend_success"
    else:
        report["results"][0]["status"] = ""
    assert check(report)


@pytest.mark.parametrize(
    "field,value",
    [
        ("host_or_browser_timeout_s", 301),
        ("host_or_browser_timeout_s", float("inf")),
        ("host_or_browser_timeout_s", float("nan")),
        ("host_or_browser_timeout_s", 0),
        ("step_timeout_s", 16),
        ("step_timeout_s", float("nan")),
        ("rss_bytes_per_tree", 2 * v.GIB + 1),
        ("rss_bytes_per_tree", True),
        ("rss_poll_ms", 51),
    ],
)
def test_finite_policy_cannot_be_relaxed_by_report(report, field, value):
    report["limits"][field] = value
    assert check(report)


@pytest.mark.parametrize(
    "field,value",
    [
        ("actual_rows", 1001),
        ("dtype", "<f4"),
        ("generator", "fake"),
        ("seed", 42),
        ("generation_chunk_rows", 1_000_001),
        ("generation_chunk_rows", 0),
        ("sha256_x_then_y", "bad"),
        ("source_peak_rss_bytes", 2 * v.GIB + 1),
    ],
)
def test_actual_source_identity_mutations(report, field, value):
    report["sources"]["1000"][field] = value
    assert check(report)


def test_source_windows_counts_bytes_and_authority_are_pinned(report):
    s = report["sources"]["1000"]
    for mutate in (
        lambda x: x["columns"]["x"].update(bytes=7999),
        lambda x: x["windows"].pop(),
        lambda x: x["windows"][0].update(kind="zoom"),
        lambda x: x["windows"][0]["window"].__setitem__(0, 0),
        lambda x: x["windows"][8].update(expected_count=432),
        lambda x: x["authority"].update(disk_guard_bytes=v.GIB),
    ):
        other = copy.deepcopy(report)
        mutate(other["sources"]["1000"])
        assert check(other)
    assert s["actual_rows"] == 1000


@pytest.mark.parametrize(
    "field,value",
    [
        ("ok", False),
        ("expected_count", 432),
        ("lit_pixels", 0),
        ("paint_hash32", -1),
        ("axes_adopt_ms", float("nan")),
        ("paint_stable_ms", 1),
        ("stability_confirmed_ms", 15001),
        ("request_start_ms", -1),
        ("request_return_ms", 15001),
    ],
)
def test_success_step_oracle_and_clock_mutations(report, field, value):
    report["results"][0]["steps"][0][field] = value
    assert check(report)


@pytest.mark.parametrize(
    "mutation", ["drop", "axes", "shape", "stale", "unadopted", "cache", "visible", "empty"]
)
def test_real_output_window_and_paint_required(report, mutation):
    c = report["results"][0]
    p = c["steps"][0]
    o = p["state"]["output"]
    if mutation == "drop":
        c["steps"].pop()
    elif mutation == "axes":
        p["state"]["axes"][0] += 1
    elif mutation == "shape":
        p["state"]["plot_shape"] = [511, 512]
    elif mutation == "stale":
        o["rendered_revision"] = 0
    elif mutation == "unadopted":
        o["adopted"] = False
    elif mutation == "cache":
        o["equivalent_cached_raster"] = True
        o["grid_value_equality_verified"] = False
    elif mutation == "visible":
        o["visible"] += 1
    else:
        c["empty_control"]["lit_pixels"] = 1
    assert check(report)


def test_arms_keep_distinct_real_oracles(report):
    plotly = next(c for c in report["results"] if c["arm"] == "plotly-aggregate")
    plotly["steps"][0]["state"]["output"]["oracle"]["grid_mass"] += 1
    assert check(report)


def test_bokeh_actual_grid_and_empty_oracle_required(report):
    c = next(c for c in report["results"] if c["arm"] == "datashader-aggregate")
    c["transport"]["checkpoints"]["empty-control"]["host_observation"]["last_output"]["count"] = 1
    assert check(report)


def test_honest_exact_fallback_and_equivalent_cache_are_allowed():
    r, historical = v.load_report(ARCHIVE / "f32-xy-cache-followup.json.gz")
    outputs = [p["state"]["output"] for c in r["results"] for p in c["steps"]]
    assert any(o["exact_fallback"] for o in outputs)
    assert any(o["equivalent_cached_raster"] for o in outputs)
    assert check(r, historical=historical) == []
    p = next(p for c in r["results"] for p in c["steps"] if p["state"]["output"]["exact_fallback"])
    p["state"]["output"]["exact_count"] += 1
    assert check(r)


@pytest.mark.parametrize(
    "mutation",
    ["negative_bytes", "wrong_delta", "over_cap", "missing_observation", "source_identity"],
)
def test_transport_memory_and_host_identity_required(report, mutation):
    c = report["results"][0]
    if mutation == "negative_bytes":
        c["steps"][0]["application_body_bytes"]["to_host"]["json_bytes"] = -1
    elif mutation == "wrong_delta":
        b = c["steps"][0]["application_body_bytes"]
        b["total_bytes"] += 1
        b["to_host"]["json_bytes"] += 1
        b["to_host"]["total_bytes"] += 1
    elif mutation == "over_cap":
        c["host_peak_rss_bytes"] = 2 * v.GIB + 1
    elif mutation == "missing_observation":
        del c["transport"]["checkpoints"]["step-0"]["host_observation"]
    else:
        c["host_meta"]["source"]["sha256_x_then_y"] = "0" * 64
    assert check(report)


def source_failures(report, status="source_failed"):
    report["sources"] = {}
    report["results"] = [
        {
            "n": 1000,
            "arm": a,
            "repetition": rep,
            "status": status,
            "detail": "source child failed before writing manifest",
            "source_peak_rss_bytes": 2 * v.GIB + 1024,
        }
        for a in v.ARMS
        for rep in range(2)
    ]
    return report


@pytest.mark.parametrize("status", ["source_failed", "source_timeout", "source_memory_limit"])
def test_complete_source_failures_are_valid_failure_evidence(report, status):
    assert check(source_failures(report, status)) == []
    assert all(c["status"] != "ok" for c in report["results"])


def test_failure_needs_reason_guard_observations_and_complete_coverage(report):
    source_failures(report)
    del report["results"][0]["source_peak_rss_bytes"]
    assert check(report)
    report["results"][0]["source_peak_rss_bytes"] = 0
    report["results"][0]["detail"] = ""
    assert check(report)
    report["results"][0]["status"] = "ok"
    assert check(report)


def test_failed_browser_cell_remains_failed(report):
    c = report["results"][0]
    c["status"] = "step_failed"
    c["steps"][-1].update(ok=False, reason="backend_oracle_not_current")
    assert check(report) == []
    c["status"] = "ok"
    assert check(report)


def hosted_failure_report(report):
    # Metadata-only fixture. Never run producer/source allocation with spoofed context.
    r = source_failures(report)
    n = 1_000_000_000
    r["sizes"] = [n]
    for c in r["results"]:
        c["n"] = n
    r["environment"]["git"].update(commit="a" * 40, dirty=False)
    r["environment"]["platform"].update(system="Darwin", machine="arm64")
    r["limits"]["rss_bytes_per_tree"] = 20 * v.GIB
    r["authority"] = [
        {
            "authority": "manual-main-macos-M4",
            "actual_rows": n,
            "source_file_bytes": 16 * n,
            "per_tree_rss_guard_bytes": 20 * v.GIB,
            "disk_guard_bytes": 20 * v.GIB,
            "mapped_bytes_are_not_rss": True,
            "facts": {**v.CONTEXT, "system": "Darwin", "machine": "arm64", "memory": 48 * v.GIB},
        }
    ]
    return r


def test_large_report_self_claim_is_not_authority(report):
    r = hosted_failure_report(report)
    assert check(r)
    assert check(r, expected_sha="a" * 40)
    ambient = {**v.CONTEXT, "GITHUB_SHA": "a" * 40}
    assert v.validate(r, expected_sha="a" * 40, environ=ambient, host=("Darwin", "arm64")) == []
    for k in v.CONTEXT:
        env = {**ambient, k: "wrong"}
        assert v.validate(r, expected_sha="a" * 40, environ=env, host=("Darwin", "arm64"))
    assert v.validate(r, expected_sha="b" * 40, environ=ambient, host=("Darwin", "arm64"))
    r["environment"]["git"]["dirty"] = True
    assert v.validate(r, expected_sha="a" * 40, environ=ambient, host=("Darwin", "arm64"))


def test_hosted_disk_limit_is_20_gib_even_if_producer_allows_200(report):
    r = hosted_failure_report(report)
    r["authority"][0]["disk_guard_bytes"] = 21 * v.GIB
    assert v.validate(
        r,
        expected_sha="a" * 40,
        environ={**v.CONTEXT, "GITHUB_SHA": "a" * 40},
        host=("Darwin", "arm64"),
    )


@pytest.mark.parametrize(
    "key",
    [
        "benchmarks/bench_density_comparison.py",
        "python/xyg:tree_sha256",
        "crates:tree_sha256",
        "js/src:tree_sha256",
        "python/xyg/static/index.js",
    ],
)
def test_existing_artifact_digests_are_checked(report, tmp_path, key):
    # A self-consistent report hash does not establish correspondence to an existing file/tree.
    if key.endswith(":tree_sha256"):
        folder = tmp_path / key.split(":")[0]
        folder.mkdir(parents=True)
        (folder / "different.py").write_text("different bytes")
    else:
        file = tmp_path / key
        file.parent.mkdir(parents=True)
        file.write_text("different bytes")
    assert check(report, artifact_root=tmp_path)


def test_loaded_native_and_harness_identity_required(report, tmp_path):
    p = report["provenance_sha256"]
    loaded = next(k for k in p if k.startswith("loaded_native:"))
    del p[loaded]
    assert check(report)
    native = tmp_path / "libxyg_core.dylib"
    native.write_bytes(b"actual binary")
    p["loaded_native:" + str(native)] = p["target/release/libxyg_core.so"]
    assert check(report, artifact_root=tmp_path)


def test_cli_json_gzip_counts_external_scope_and_failure_semantics(report, tmp_path):
    path = tmp_path / "report.json"
    source_failures(report)
    path.write_text(json.dumps(report))
    result = subprocess.run(
        [sys.executable, str(SCRIPT), str(path), "--sizes", "1000", "--arms", ",".join(v.ARMS)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert "0 successful cells, 6 failed cells" in result.stdout
    assert "no gesture, kernel-win or competitive acceptance claim" in result.stdout
    mismatch = subprocess.run(
        [sys.executable, str(SCRIPT), str(path), "--sizes", "1000,100000000"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert mismatch.returncode == 1
    assert "external expected sizes" in mismatch.stderr
    archived = subprocess.run(
        [sys.executable, str(SCRIPT), str(ARCHIVE / "f32.json.gz"), "--artifact-root", str(ROOT)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert archived.returncode == 0, archived.stderr
    assert "16 successful cells, 2 failed cells" in archived.stdout


def test_decoded_report_size_bound_and_no_allocation(tmp_path, monkeypatch):
    monkeypatch.setattr(v, "MAX_REPORT_BYTES", 32)
    path = tmp_path / "oversized.json"
    path.write_bytes(b" " * 33)
    with pytest.raises(v.InvalidReport, match="decoded bound"):
        v.load_report(path)


@pytest.mark.parametrize("status", ["memory_limit", "failed(TimeoutError)"])
def test_actual_browser_supervisor_failures_are_valid(report, status):
    c = report["results"][0]
    c.update(status=status, error="browser supervisor terminated the tree")
    c["steps"] = []
    assert check(report) == []


@pytest.mark.parametrize(
    "raw", ['{"status":"ok","status":"failed"}', '{"clock":NaN}', '{"clock":Infinity}']
)
def test_json_rejects_duplicate_keys_and_nonfinite_constants(tmp_path, raw):
    path = tmp_path / "bad.json"
    path.write_text(raw)
    with pytest.raises(v.InvalidReport):
        v.load_report(path)


def test_existing_archive_name_and_self_flag_do_not_grant_historical_binding(report, tmp_path):
    report["provenance_sha256"]["benchmarks/bench_density_comparison.py"] = "0" * 64
    path = tmp_path / "f64-memmap.json.gz"
    import gzip

    with gzip.open(path, "wt") as stream:
        json.dump(report, stream)
    r, historical = v.load_report(path)
    assert historical is None
    assert r["historical_archive_commit"]
    assert check(r, artifact_root=ROOT)


@pytest.mark.parametrize("target", ["source", "host"])
def test_successful_preparation_cannot_exceed_declared_phase(report, target):
    if target == "source":
        report["sources"]["1000"]["creation_wall_ms"] = 180001
    else:
        report["results"][0]["host_prepare_wall_ms"] = 180001
    assert check(report)
