"""Equal-window/source proofs; large-row authority tests allocate no large source."""

from __future__ import annotations

import gzip
import hashlib
import json
from pathlib import Path

import numpy as np
import pytest
from benchmarks._ux_comparison_data import make_data
from benchmarks._ux_comparison_source import (
    allocation_guard,
    count_window,
    create_source,
    inventory,
    load_source,
    windows,
)


def test_same_24_pans_eight_adjacent_zooms_and_f32_source(tmp_path):
    meta = create_source(tmp_path / "source", 1000, "f32", chunk=127)
    x, y, loaded = load_source(tmp_path / "source/source.json", 1000)
    a, b = make_data(1000)
    np.testing.assert_array_equal(x, a)
    np.testing.assert_array_equal(y, b)
    assert meta == loaded
    assert meta["sha256_x_then_y"] == hashlib.sha256(a.tobytes() + b.tobytes()).hexdigest()
    steps = windows(meta["extents"])
    assert len(steps) == 32
    assert [s["kind"] for s in steps] == ["pan"] * 24 + ["zoom"] * 8
    zooms = steps[24:]
    assert (zooms[1]["window"][1] - zooms[1]["window"][0]) == pytest.approx(
        2 * (zooms[0]["window"][1] - zooms[0]["window"][0])
    )
    for step in meta["windows"]:
        assert step["expected_count"] == count_window(a, b, step["window"], chunk=13)
    assert count_window(x, y, [100, 101, 100, 101], chunk=64) == 0


def test_f64_map_is_chunk_invariant_real_and_retains_pointers(tmp_path):
    first = create_source(tmp_path / "a", 1000, "f64-memmap", chunk=19)
    second = create_source(tmp_path / "b", 1000, "f64-memmap", chunk=257)
    assert first["sha256_x_then_y"] == second["sha256_x_then_y"]
    assert sum(c["bytes"] for c in first["columns"].values()) == 16000
    x, y, _ = load_source(tmp_path / "a/source.json", 1000)
    assert isinstance(x, np.memmap) and isinstance(y, np.memmap)
    observed = inventory((x, y), (x.view(np.ndarray), y.view(np.ndarray)))
    assert all(
        v["pointer_equal"] and v["shares_memory"] and v["retained_mapped"]
        for v in observed.values()
    )
    assert count_window(x, y, first["extents"]) == 1000
    # Corruption is a source failure, never a row-count-only pass.
    with (tmp_path / "a/x.f64-memmap").open("r+b") as stream:
        stream.write(b"broken!!")
    with pytest.raises(ValueError, match="hash mismatch"):
        load_source(tmp_path / "a/source.json", 1000)


def test_allocation_guard_precedes_files_and_does_not_confuse_mapped_size_with_rss(tmp_path):
    directory = tmp_path / "forbidden"
    with pytest.raises(ValueError, match="over 1M"):
        create_source(directory, 1_000_001, "f64-memmap", disk_gib=0.25)
    assert not directory.exists()
    with pytest.raises(ValueError, match="RSS guard"):
        allocation_guard(1000, "f32", rss_gib=3)
    with pytest.raises(ValueError, match="disk guard"):
        allocation_guard(1000, "f32", disk_gib=1)
    facts = {
        "GITHUB_ACTIONS": "true",
        "GITHUB_EVENT_NAME": "workflow_dispatch",
        "GITHUB_REF": "refs/heads/main",
        "GITHUB_WORKFLOW": "Interactive ceiling benchmark",
        "RUNNER_OS": "macOS",
        "system": "Darwin",
        "machine": "arm64",
        "memory": 48 * 2**30,
    }
    authorized = allocation_guard(1_000_000_000, "f64-memmap", rss_gib=20, disk_gib=32, facts=facts)
    assert authorized["source_file_bytes"] == 16_000_000_000
    assert authorized["mapped_bytes_are_not_rss"] is True
    for key, value in [
        ("GITHUB_REF", "refs/heads/other"),
        ("system", "Linux"),
        ("GITHUB_EVENT_NAME", "push"),
    ]:
        with pytest.raises(ValueError, match="over 1M"):
            allocation_guard(
                1_000_000_000, "f64-memmap", rss_gib=20, disk_gib=32, facts={**facts, key: value}
            )


def test_original_archive_is_bound_to_historical_commit_not_current_harness():
    root = Path(__file__).resolve().parents[1]
    directory = root / "benchmarks/results/live-aggregation-2026-10-24"
    report = json.loads((directory / "bounded.json").read_text())
    assert (
        hashlib.sha256((directory / "bounded.json").read_bytes()).hexdigest()
        == "9917683d0175dd026fd3e9683bcadac498b9e34d1a761388e212303370e6a083"
    )
    assert report["environment"]["git"]["commit"] == "71e48b67827709ed251ae05b90d010a8cef824eb"
    # Its dirty-tree sources were committed as 51975d5d. Do not demand those
    # raw producer hashes match evolved code, and never rewrite the archive.
    old_hash = report["provenance_sha256"]["benchmarks/bench_ux.py"]
    assert len(old_hash) == 64


@pytest.mark.parametrize("child", [False, True])
def test_legacy_ux_rejects_large_source_before_generation_or_output(monkeypatch, tmp_path, child):
    pytest.importorskip("websocket")
    from benchmarks import bench_ux

    output = tmp_path / "not-created.json"
    called = []

    def forbidden(*args, **kwargs):
        called.append(True)
        raise AssertionError("unbounded controller or builder allocation")

    monkeypatch.setattr(bench_ux, "make_data", forbidden)
    monkeypatch.setattr(bench_ux, "plotly_artifact", forbidden)
    argv = (
        [
            "bench_ux.py",
            "--plotly-build-child",
            "--build-n",
            "1000001",
            "--build-artifact",
            str(output),
        ]
        if child
        else ["bench_ux.py", "--sizes", "1000001", "--memory-gib", "0.01", "--out", str(output)]
    )
    monkeypatch.setattr("sys.argv", argv)
    with pytest.raises(SystemExit) as rejected:
        bench_ux.main()
    assert rejected.value.code == 2
    assert called == []
    assert not output.exists()


def test_new_controller_rejects_large_local_source_before_launch_or_directory(
    monkeypatch, tmp_path
):
    pytest.importorskip("websocket")
    from benchmarks import bench_density_comparison as runner

    output = tmp_path / "not-created" / "result.json"

    def forbidden(*args, **kwargs):
        raise AssertionError(
            "source child or temporary directory created before allocation authority"
        )

    monkeypatch.setattr(runner.subprocess, "Popen", forbidden)
    monkeypatch.setattr(runner.tempfile, "TemporaryDirectory", forbidden)
    monkeypatch.setattr(
        "sys.argv",
        [
            "bench_density_comparison.py",
            "--sizes",
            "1000001",
            "--profile",
            "f64-memmap",
            "--memory-gib",
            "2",
            "--disk-gib",
            "0.25",
            "--chrome",
            "unused",
            "--out",
            str(output),
        ],
    )
    with pytest.raises(SystemExit) as rejected:
        runner.main()
    assert rejected.value.code == 2
    assert not output.parent.exists()


@pytest.mark.parametrize(
    ("flag", "value"),
    [
        ("--timeout", "nan"),
        ("--timeout", "inf"),
        ("--timeout", "301"),
        ("--timeout", "0"),
        ("--step-timeout", "nan"),
        ("--step-timeout", "inf"),
        ("--step-timeout", "16"),
        ("--step-timeout", "0"),
    ],
)
def test_comparison_rejects_invalid_deadlines_before_source_allocation(
    monkeypatch, tmp_path, flag, value
):
    pytest.importorskip("websocket")
    from benchmarks import bench_density_comparison as runner

    output = tmp_path / "not-created" / "result.json"

    def forbidden(*args, **kwargs):
        pytest.fail("invalid deadline reached source allocation")

    monkeypatch.setattr(runner.subprocess, "Popen", forbidden)
    monkeypatch.setattr(runner.tempfile, "TemporaryDirectory", forbidden)
    monkeypatch.setattr(
        "sys.argv",
        [
            "bench_density_comparison.py",
            "--sizes",
            "1000",
            "--chrome",
            "unused",
            "--out",
            str(output),
            flag,
            value,
        ],
    )
    with pytest.raises(SystemExit) as rejected:
        runner.main()
    assert rejected.value.code == 2
    assert not output.parent.exists()


@pytest.mark.parametrize("hardware", [False, True])
@pytest.mark.parametrize("inherited", ["0", "1"])
def test_saved_renderer_mode_uses_cli_even_with_opposite_ambient_env(
    monkeypatch, tmp_path, hardware, inherited
):
    pytest.importorskip("websocket")
    from benchmarks import bench_density_comparison as runner

    monkeypatch.setenv("XY_BENCH_HARDWARE_GL", inherited)
    output = tmp_path / "report.json"
    # A real bounded source child times out before imports; no browser is launched.
    monkeypatch.setattr(
        "sys.argv",
        [
            "bench_density_comparison.py",
            "--sizes",
            "5",
            "--arms",
            "xy-density",
            "--chrome",
            "unused",
            "--timeout",
            "0.001",
            "--out",
            str(output),
            *(["--hardware"] if hardware else []),
        ],
    )
    runner.main()
    report = json.loads(output.read_text())
    expected = "hardware" if hardware else "software-gl"
    assert report["environment"]["browser_renderer"] == expected
    assert report["environment"]["browser_renderer_requested"] == expected
    assert report["environment"]["browser_renderer_observed"] is None
    assert report["environment"]["browser_renderer_scope"] == (
        "launch-request; actual renderer not measured"
    )
    assert {row["status"] for row in report["results"]} == {"source_timeout"}


def test_retained_equal_window_profiles_oracles_modes_and_historical_producers():
    """Offline integrity of actual browser observations; never a stubbed run."""
    root = Path(__file__).resolve().parents[1]
    directory = root / "benchmarks/results/live-aggregation-2026-10-24/equal-window-v2"
    reports = {
        name: json.loads(gzip.decompress((directory / (name + ".gz")).read_bytes()))
        for name in ("f32.json", "f32-xy-cache-followup.json", "f64-memmap.json")
    }
    initial = reports["f32.json"]
    historical = json.loads((directory.parent / "bounded.json").read_text())
    assert len(initial["results"]) == 18
    for n, source in initial["sources"].items():
        assert source["sha256_x_then_y"] == historical["sources"][n]["sha256_x_then_y"]
    # Retain both strict-pointer diagnostic failures, without turning them into successes.
    failures = [r for r in initial["results"] if r["status"] != "ok"]
    assert len(failures) == 2
    for row in failures:
        assert row["arm"] == "xy-density" and row["n"] == 1_000_000
        assert row["status"] == "step_failed"
        assert row["steps"][-1]["diag"]["snap"]["hash"] == row["steps"][3]["paint_hash32"]
    repairs = reports["f32-xy-cache-followup.json"]
    assert len(repairs["results"]) == 2
    for row in repairs["results"]:
        assert row["status"] == "ok" and len(row["steps"]) == 32
        cached = [
            s["state"]["output"]
            for s in row["steps"]
            if s["state"]["output"].get("equivalent_cached_raster")
        ]
        assert cached
        assert all(c["grid_value_equality_verified"] for c in cached)
        assert any(c["rendered_revision"] < c["revision"] for c in cached)
    assert len(reports["f64-memmap.json"]["results"]) == 18
    for name, report in reports.items():
        producer = directory / ("f32-producer" if name == "f32.json" else "current-producer")
        for path, digest in report["provenance_sha256"].items():
            if path.startswith("benchmarks/"):
                assert (
                    hashlib.sha256((producer / (path + ".txt")).read_bytes()).hexdigest() == digest
                )
        for row in report["results"]:
            if row["status"] != "ok":
                continue
            source = report["sources"][str(row["n"])]
            assert len(row["steps"]) == 32 and row["empty_control"]["ok"] is True
            assert row["empty_control"]["lit_pixels"] == 0
            assert row["host_meta"]["source"]["sha256_x_then_y"] == source["sha256_x_then_y"]
            assert row["host_meta"]["source"]["actual_rows"] == row["n"]
            assert sum(c["bytes"] for c in source["columns"].values()) == row["n"] * (
                16 if report["profile"] == "f64-memmap" else 8
            )
            for step, request in zip(row["steps"], source["windows"], strict=True):
                assert step["ok"] is True
                assert step["kind"] == request["kind"]
                assert step["requested_window"] == request["window"]
                assert step["expected_count"] == request["expected_count"]
                assert np.allclose(step["state"]["axes"], request["window"], rtol=0, atol=1e-9)
                assert step["state"]["plot_shape"] == [512, 512]
                out = step["state"]["output"]
                assert out["adopted"] is True
                if out["exact_fallback"]:
                    assert row["arm"] == "xy-density"
                    assert out["exact_count"] == request["expected_count"]
                    assert out["payload_count"] >= out["exact_count"]
                else:
                    assert np.allclose(out["domain"], request["window"], rtol=0, atol=1e-9)
                    assert all(0 < v <= 512 for v in out["raster_shape"])
                if out.get("oracle"):
                    assert (
                        out["oracle"]["passed"]
                        and out["oracle"]["count"] == request["expected_count"]
                    )
                observation = step["host_observation"]
                if row["arm"] == "datashader-aggregate":
                    assert observation["last_output"]["passed"] is True
                    assert observation["last_output"]["grid_mass"] == request["expected_count"]
                    assert np.allclose(
                        observation["last_output"]["domain"], request["window"], rtol=0, atol=1e-9
                    )
                for value in step["memory"].values():
                    assert value > 0
                assert step["memory"]["host_peak_rss_bytes"] >= step["memory"]["host_rss_bytes"]
                assert (
                    step["memory"]["browser_peak_rss_bytes"] >= step["memory"]["browser_rss_bytes"]
                )
                for col in observation["canonical_admission"].values():
                    for key in (
                        "pointer_equal",
                        "shares_memory",
                        "source_mapped",
                        "retained_mapped",
                    ):
                        assert isinstance(col[key], bool)
                    if report["profile"] == "f64-memmap":
                        assert col["source_mapped"] is True
    for line in (directory / "SHA256SUMS").read_text().splitlines():
        digest, path = line.split("  ", 1)
        assert hashlib.sha256((directory / path).read_bytes()).hexdigest() == digest
