from __future__ import annotations

import argparse
import gc
import importlib.util
import json
import subprocess
import sys
import time
from pathlib import Path

import pytest

import xyg

ROOT = Path(__file__).resolve().parents[1]


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


bench = _load("bench_density_e2e", ROOT / "benchmarks" / "bench_density_e2e.py")
verify = _load("verify_density_e2e_report", ROOT / "scripts" / "verify_density_e2e_report.py")


def _report() -> dict:
    return {
        "schema_version": 1,
        "report_kind": "density-e2e",
        "status": "ok",
        "authority": False,
        "authority_context": {
            "github_ref": "refs/pull/876/merge",
            "github_event_name": "pull_request",
            "capability": False,
        },
        "point_count": 250_000,
        "environment": {
            "generated_at_utc": "2026-09-04T12:34:56Z",
            "python": {
                "version": "3.11.9",
                "implementation": "CPython",
                "compiler": "GCC 13",
            },
            "platform": {
                "system": "Linux",
                "release": "6.8.0",
                "version": "Ubuntu",
                "machine": "x86_64",
                "processor": "",
            },
            "cpu_count": 4,
            "package_versions": {"xyg": "0.1.0"},
            "executables": {
                "node": "v22.0.0",
                "rustc": "rustc 1.96.0",
                "cargo": "cargo 1.96.0",
                "chromium": "Chromium 140.0",
            },
            "xy_backend": "native",
            "browser_renderer": "software-gl",
            "git": {"commit": "a" * 40, "branch": "feature", "dirty": False},
        },
        "limits": {
            "timeout_seconds": 180,
            "first_payload_bytes": 4_194_304,
            "source_ratio": 0.1,
            "max_tree_rss_bytes": 4 * 1024**3,
            "max_disk_bytes": 1024**3,
            "derived_cache_ratio": 0.1,
            "refine_payload_bytes": 4_194_304,
        },
        "source": {
            "bytes": 4_000_000,
            "x_bytes": 2_000_000,
            "y_bytes": 2_000_000,
            "backing": "mmap-f64",
            "generator": "diagonal-band-v1",
            "chunk_points": 250_000,
            "x_sha256": "a" * 64,
            "y_sha256": "b" * 64,
        },
        "count_oracle": {
            "backend": "native-bin2d",
            "expected_count": 250_000,
            "observed_count": 250_000,
            "recomposed_count": 250_000,
            "recomposed_absolute_error": 0.0,
            "match": True,
            "grid_width": 512,
            "grid_height": 384,
            "grid_bytes": 786_432,
            "grid_sha256": "9" * 64,
            "product_link": {
                "route": "exact-bin2d",
                "emitted_buffer_index": 0,
                "emitted_buffer_bytes": 196_608,
                "emitted_buffer_sha256": "e" * 64,
                "oracle_encoded_bytes": 196_608,
                "oracle_encoded_sha256": "e" * 64,
                "emitted_max": 512.0,
                "oracle_max": 512.0,
                "encoded_match": True,
                "max_match": True,
                "emitted_binning": "exact",
                "recomposed_binning": "exact",
                "pyramid_level": None,
                "pyramid_base_dim": 0,
            },
        },
        "payload": {
            "bytes": 262_408,
            "spec_json_bytes": 10_000,
            "wire_bytes": 272_408,
            "buffer_count": 3,
            "canonical_f64_buffers": 0,
            "classes": {
                "u8": {"buffers": 1, "bytes": 196_608},
                "offset-f32": {"buffers": 2, "bytes": 65_800},
            },
            "raw_source_ratio": 0.065602,
            "source_ratio": 0.068102,
            "semantics": {
                "trace_count": 1,
                "trace_id": 0,
                "kind": "scatter",
                "tier": "density",
                "n_points": 250_000,
                "visible": 250_000,
                "n_marks": 196_608,
                "reduction": "bin2d",
                "binning": "exact",
                "encoding": "log-u8",
                "grid_width": 512,
                "grid_height": 384,
                "grid_cells": 196_608,
                "sample_mode": "sampled",
                "sample_points": 8_225,
                "sample_visible": 250_000,
            },
            "determinism": {"checked": True, "match": True},
            "spec_sha256": "c" * 64,
            "fingerprint_sha256": "d" * 64,
            "buffer_sha256": ["e" * 64, "f" * 64, "0" * 64],
        },
        "host_memory_report": {
            "canonical_bytes": 0,
            "canonical_mapped_bytes": 4_000_000,
            "resident_array_bytes": 0,
            "pyramid_bytes": 0,
            "pyramid_spilled_bytes": 0,
        },
        "process_tree": {
            "peak_rss_bytes": 500_000_000,
            "peak_temp_bytes": 4_100_000,
            "peak_process_count": 2,
            "peak_pids": [100, 101],
            "max_live_process_count": 2,
            "observed_process_count": 2,
            "observed_processes": [
                {"pid": 100, "name": "python3"},
                {"pid": 101, "name": "chrome"},
            ],
            "browser_process_observed": True,
            "worker_peak_rss_bytes": 100_000_000,
        },
        "phases": {
            name: {"seconds": 0.1, "rss": {"rss_bytes": 1, "peak_rss_bytes": 1}}
            for name in (
                "source_creation",
                "source_admission",
                "native_aggregation_build",
                "native_count_oracle",
                "determinism_rebuild",
                "browser_journey",
            )
        },
        "host_refine": {
            "seconds": 0.01,
            "oracle_seconds": 0.02,
            "audit_after_browser_done": True,
            "reply_bytes": 15_580,
            "wire_bytes": 21_100,
            "raw_source_ratio": 0.003895,
            "source_ratio": 0.005275,
            "request_window": {
                "trace": 0,
                "x0": 0.25,
                "x1": 0.5,
                "y0": 0.0,
                "y1": 1.0,
                "w": 502,
                "h": 348,
            },
            "semantics": {
                "message_type": "density_update",
                "trace_count": 1,
                "trace_id": 0,
                "mode": "density",
                "tier": "density",
                "visible": 62_500,
                "reduction": "bin2d-oversized",
                "binning": "bin2d-oversized",
                "encoding": "log-u8",
                "grid_width": 164,
                "grid_height": 95,
            },
            "buffer_inventory": {
                "classes": {"u8": {"buffers": 1, "bytes": 15_580}},
                "buffer_count": 1,
                "bytes": 15_580,
                "buffer_sha256": ["2" * 64],
            },
            "product_link_oracle": {
                "backend": "native-bin2d",
                "expected_visible": 62_500,
                "observed_count": 62_500.0,
                "recomposed_count": 62_500.0,
                "recomposed_absolute_error": 0.0,
                "count_match": True,
                "grid_width": 164,
                "grid_height": 95,
                "grid_bytes": 62_320,
                "grid_sha256": "7" * 64,
                "product_link": {
                    "route": "exact-bin2d",
                    "emitted_buffer_index": 0,
                    "emitted_buffer_bytes": 15_580,
                    "emitted_buffer_sha256": "2" * 64,
                    "oracle_encoded_bytes": 15_580,
                    "oracle_encoded_sha256": "2" * 64,
                    "emitted_max": 64.0,
                    "oracle_max": 64.0,
                    "encoded_match": True,
                    "max_match": True,
                    "emitted_binning": "bin2d-oversized",
                    "emitted_reduction": "bin2d-oversized",
                    "recomposed_binning": "bin2d-oversized",
                    "pyramid_level": None,
                    "pyramid_base_dim": 0,
                },
            },
        },
        "browser": {
            "initial_payload_bytes": 262_408,
            "initial_spec_json_bytes": 10_000,
            "initial_wire_bytes": 272_408,
            "strict_csp": True,
            "csp_inline_blocked": True,
            "unexpected_requests": [],
            "renderer": "ANGLE (SwiftShader)",
            "view_transform": {
                "kind": "in-domain-x-zoom-pan",
                "x_span_fraction": 0.25,
                "x_offset_fraction": 0.25,
                "y_span_fraction": 1,
                "home": {"x0": 0.0, "x1": 1.0, "y0": 0.0, "y1": 1.0},
                "requested": {"x0": 0.25, "x1": 0.5, "y0": 0.0, "y1": 1.0},
                "applied": {"x0": 0.25, "x1": 0.5, "y0": 0.0, "y1": 1.0},
                "applied_matches_requested": True,
            },
            "request_window": {
                "trace": 0,
                "x0": 0.25,
                "x1": 0.5,
                "y0": 0.0,
                "y1": 1.0,
                "w": 502,
                "h": 348,
            },
            "prefers_reduced_motion": False,
            "view_destroyed": True,
            "server_stopped": True,
            "browser_exited": True,
            "first_paint": {"construct_upload_ms": 2.0, "settle_ms": 3.0},
            "refine": {
                "roundtrip_ms": 4.0,
                "apply_paint_ms": 1.0,
                "reply_bytes": 15_580,
                "wire_bytes": 21_100,
                "buffer_sha256": ["2" * 64],
                "upload": {"calls": 0, "bytes": 0, "call_ms": 0.0},
                "application": "facts-only",
                "texture_changed": False,
                "facts_cache_delta": 1,
                "mode": "density",
                "binning": "bin2d-oversized",
                "semantics": {
                    "message_type": "density_update",
                    "trace_count": 1,
                    "trace_id": 0,
                    "mode": "density",
                    "tier": "density",
                    "visible": 62_500,
                    "reduction": "bin2d-oversized",
                    "binning": "bin2d-oversized",
                    "encoding": "log-u8",
                    "grid_width": 164,
                    "grid_height": 95,
                },
                "transition_mode": "normal",
                "transition_settled": True,
            },
            "requests": ["density_view"],
            "initial_upload": {"calls": 3, "bytes": 262_408, "call_ms": 0.5},
            "first_pixels": {
                "region": "plot",
                "width": 640,
                "height": 400,
                "bytes": 1_024_000,
                "non_background_pixels": 100,
                "sha256": "1" * 64,
            },
            "refined_pixels": {
                "region": "plot",
                "width": 640,
                "height": 400,
                "bytes": 1_024_000,
                "non_background_pixels": 110,
                "sha256": "3" * 64,
            },
        },
        "cleanup": {
            "mmap_closed": True,
            "figure_released": True,
            "temp_tree_removed": True,
            "worker_exit_code": 0,
            "orphan_pids_after_reap": [],
        },
    }


def test_report_contract_accepts_complete_small_scale_evidence() -> None:
    assert verify.validate(_report(), expected_sha="a" * 40) == []


def test_report_contract_rejects_noncanonical_point_count() -> None:
    report = _report()
    report["point_count"] = 2_000_000
    assert any("canonical 250k, 1M, or 100M" in error for error in verify.validate(report))


@pytest.mark.parametrize(
    ("points", "binning", "reduction", "initial", "refine"),
    [
        (250_000, "exact", "bin2d", True, False),
        (1_000_000, "pyramid-L2", "pyramid-count", False, False),
        (1_000_000, "bin2d-oversized", "bin2d-oversized", False, True),
        (1_000_000, "bin2d-oversized", "pyramid-count", False, False),
        (100_000_000, "pyramid-L3", "pyramid-count", True, True),
        (100_000_000, "pyramid-L3-tiles", "pyramid-count", False, False),
        (100_000_000, "pyramid-L3-upsampled", "pyramid-count", False, False),
        (100_000_000, "pyramid-L999", "pyramid-count", False, False),
    ],
)
def test_harness_semantic_routes_are_scale_exact(
    points: int, binning: str, reduction: str, initial: bool, refine: bool
) -> None:
    assert bench._initial_density_relation(binning, reduction, points) is initial
    assert bench._refine_density_relation(binning, reduction, points) is refine


def test_real_resident_pyramid_oracle_links_emitted_grid(tmp_path: Path) -> None:
    points = bench.PYRAMID_MIN_POINTS
    x, y, _ = bench._generate_sources(tmp_path, points, bench.MAX_CHUNK_POINTS)
    figure = xyg.scatter_chart(xyg.scatter(x, y, density=True), width=640, height=400).figure()
    try:
        spec, raw_buffers = figure.build_payload_split()
        oracle = bench._native_count_oracle(
            x, y, figure, spec, [bytes(item) for item in raw_buffers], points
        )
        assert oracle["backend"] == "native-resident-pyramid"
        assert oracle["observed_count"] == points
        assert oracle["recomposed_absolute_error"] < 0.5
        assert oracle["match"] is True
        link = oracle["product_link"]
        assert link["route"] == "resident-pyramid"
        assert link["encoded_match"] is True
        assert link["max_match"] is True
        assert link["emitted_binning"] == link["recomposed_binning"] == "pyramid-L2"
        assert link["pyramid_level"] == 2
        assert link["pyramid_base_dim"] == 2048
        assert link["emitted_buffer_sha256"] == link["oracle_encoded_sha256"]
    finally:
        figure = None
        gc.collect()
        for mapping in (x, y):
            mapped = getattr(mapping, "_mmap", None)
            if mapped is not None:
                mapped.close()


def _authority_report() -> dict:
    report = _report()
    points = 100_000_000
    source_bytes = points * 16
    report.update(
        point_count=points,
        authority=True,
        authority_context={
            "github_ref": "refs/heads/main",
            "github_event_name": "schedule",
            "capability": True,
        },
    )
    report["source"].update(
        bytes=source_bytes,
        x_bytes=points * 8,
        y_bytes=points * 8,
    )
    report["host_memory_report"]["canonical_mapped_bytes"] = source_bytes
    report["payload"].update(
        raw_source_ratio=report["payload"]["bytes"] / source_bytes,
        source_ratio=report["payload"]["wire_bytes"] / source_bytes,
    )
    report["payload"]["semantics"].update(
        n_points=points,
        visible=points,
        sample_visible=points,
        reduction="pyramid-count",
        binning="pyramid-L3",
    )
    report["host_memory_report"].update(
        pyramid_bytes=89_478_484,
        pyramid_spilled_bytes=0,
    )
    report["count_oracle"].update(
        backend="native-resident-pyramid",
        expected_count=points,
        observed_count=points,
        recomposed_count=points,
    )
    report["count_oracle"]["product_link"].update(
        route="resident-pyramid",
        emitted_binning="pyramid-L3",
        recomposed_binning="pyramid-L3",
        pyramid_level=3,
        pyramid_base_dim=4096,
    )
    report["host_refine"].update(
        raw_source_ratio=report["host_refine"]["reply_bytes"] / source_bytes,
        source_ratio=report["host_refine"]["wire_bytes"] / source_bytes,
    )
    report["host_refine"]["semantics"].update(
        visible=25_000_000,
        reduction="pyramid-count",
        binning="pyramid-L1",
    )
    report["host_refine"]["product_link_oracle"].update(
        backend="native-resident-pyramid",
        expected_visible=25_000_000,
        observed_count=25_000_000.0,
        recomposed_count=25_000_000.0,
    )
    report["host_refine"]["product_link_oracle"]["product_link"].update(
        route="resident-pyramid",
        emitted_binning="pyramid-L1",
        emitted_reduction="pyramid-count",
        recomposed_binning="pyramid-L1",
        pyramid_level=1,
        pyramid_base_dim=4096,
    )
    report["browser"]["refine"]["semantics"].update(
        visible=25_000_000,
        reduction="pyramid-count",
        binning="pyramid-L1",
    )
    report["browser"]["refine"]["binning"] = "pyramid-L1"
    report["browser"]["view_transform"].update(
        x_span_fraction=0.2,
        x_offset_fraction=0.25,
        requested={"x0": 0.25, "x1": 0.45, "y0": 0.0, "y1": 1.0},
        applied={"x0": 0.25, "x1": 0.45, "y0": 0.0, "y1": 1.0},
    )
    report["browser"]["refine"].update(
        application="texture",
        texture_changed=True,
        facts_cache_delta=1,
        upload={"calls": 1, "bytes": 15_580, "call_ms": 0.1},
    )
    return report


def test_report_contract_accepts_rust_owned_100m_pyramid_semantics() -> None:
    report = _authority_report()

    assert verify.validate(report, expected_sha="a" * 40) == []


@pytest.mark.parametrize(
    "mutation",
    [
        lambda report: report["payload"]["semantics"].update(binning="exact", reduction="bin2d"),
        lambda report: report["payload"]["semantics"].update(binning="pyramid-L3-tiles"),
        lambda report: report["payload"]["semantics"].update(binning="pyramid-L3-upsampled"),
        lambda report: report["payload"]["semantics"].update(binning="pyramid-L999"),
        lambda report: report["host_refine"]["semantics"].update(binning="pyramid-L2-tiles"),
        lambda report: report["host_memory_report"].update(pyramid_bytes=0),
        lambda report: report["host_memory_report"].update(pyramid_spilled_bytes=1),
    ],
)
def test_report_contract_rejects_wrong_or_tiled_100m_routing(mutation) -> None:
    report = _authority_report()
    mutation(report)
    assert any(
        "scale-required density route" in error or "resident pyramid" in error
        for error in verify.validate(report)
    )


def test_report_contract_requires_100m_texture_application_and_aligned_ladder() -> None:
    report = _authority_report()
    report["browser"]["refine"].update(
        application="facts-only",
        texture_changed=False,
        facts_cache_delta=1,
        upload={"calls": 0, "bytes": 0, "call_ms": 0.0},
    )
    assert any("100M authority refine" in error for error in verify.validate(report))

    report = _authority_report()
    reply_bytes = report["host_refine"]["reply_bytes"]
    report["browser"]["refine"]["upload"] = {
        "calls": 26,
        "bytes": 26 * reply_bytes,
        "call_ms": 1.5,
    }
    assert verify.validate(report, expected_sha="a" * 40) == []

    report["browser"]["refine"]["upload"]["calls"] = 65
    report["browser"]["refine"]["upload"]["bytes"] = 65 * reply_bytes
    assert any("positive bounded GPU upload" in error for error in verify.validate(report))

    report = _authority_report()
    report["browser"]["refine"]["upload"].update(calls=2, bytes=20_000)
    assert any("positive bounded GPU upload" in error for error in verify.validate(report))

    report = _authority_report()
    report["browser"]["request_window"]["x1"] = 0.6
    report["host_refine"]["request_window"]["x1"] = 0.6
    assert any("density_view window" in error for error in verify.validate(report))


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (lambda report: report["payload"].update(canonical_f64_buffers=1), "zero canonical"),
        (
            lambda report: report["payload"].update(
                bytes=5_000_000,
                spec_json_bytes=10_000,
                wire_bytes=5_010_000,
                raw_source_ratio=1.25,
                source_ratio=1.2525,
            ),
            "exceeds",
        ),
        (
            lambda report: report["process_tree"].update(peak_rss_bytes=5 * 1024**3),
            "peak RSS exceeds",
        ),
        (
            lambda report: report["process_tree"].update(
                observed_process_count=1,
                observed_processes=[{"pid": 100, "name": "python3"}],
            ),
            "worker and descendants",
        ),
        (
            lambda report: report["process_tree"].update(browser_process_observed=False),
            "Chromium descendant",
        ),
        (
            lambda report: report["process_tree"].update(worker_peak_rss_bytes=600_000_000),
            "VmHWM backstop",
        ),
        (lambda report: report["cleanup"].update(orphan_pids_after_reap=[123]), "no process-group"),
    ],
)
def test_report_contract_rejects_hard_failures(mutation, message: str) -> None:
    report = _report()
    mutation(report)
    assert any(message in error for error in verify.validate(report))


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (lambda report: report["source"].update(x_bytes=1), "exactly point_count"),
        (lambda report: report["source"].update(generator="uniform"), "diagonal-band-v1"),
        (lambda report: report["source"].update(chunk_points=100_000_000), "chunk_points"),
        (lambda report: report["source"].update(x_sha256="not-a-hash"), "SHA-256"),
        (lambda report: report["environment"]["git"].update(dirty=True), "dirty"),
        (lambda report: report["environment"].pop("executables"), "Node, Rust"),
        (lambda report: report["payload"]["classes"].pop("u8"), "u8 density"),
        (
            lambda report: report["payload"].update(wire_bytes=200_000),
            "spec JSON plus raw",
        ),
        (lambda report: report["payload"].update(source_ratio=0.0), "source ratio"),
        (
            lambda report: report["payload"]["semantics"].update(binning="javascript-fallback"),
            "scale-required",
        ),
        (
            lambda report: report["payload"]["semantics"].update(
                binning="pyramid-L3", reduction="pyramid-count"
            ),
            "scale-required",
        ),
        (
            lambda report: report["count_oracle"].update(observed_count=249_999),
            "equal point_count exactly",
        ),
        (
            lambda report: report["count_oracle"].update(
                recomposed_count=249_999.4,
                recomposed_absolute_error=0.6,
            ),
            "sub-point bound",
        ),
        (
            lambda report: report["count_oracle"]["product_link"].update(
                emitted_buffer_sha256="8" * 64
            ),
            "product-link oracle",
        ),
        (
            lambda report: report["count_oracle"]["product_link"].update(emitted_max=511.0),
            "product-link oracle",
        ),
        (
            lambda report: report["host_refine"]["buffer_inventory"].update(
                classes={"f64": {"buffers": 1, "bytes": 100_000}}
            ),
            "only the bounded u8",
        ),
        (
            lambda report: report["host_refine"].update(source_ratio=0.0),
            "wire source ratio",
        ),
        (
            lambda report: report["host_refine"].pop("oracle_seconds"),
            "outside product response time",
        ),
        (
            lambda report: report["host_refine"].update(audit_after_browser_done=False),
            "after browser timing and paint complete",
        ),
        (
            lambda report: report["host_refine"].update(wire_bytes=20_000),
            "base64 JSON envelope",
        ),
        (
            lambda report: report["host_refine"]["semantics"].update(binning="javascript-fallback"),
            "scale-required",
        ),
        (
            lambda report: report["host_refine"]["semantics"].update(reduction="pyramid-count"),
            "scale-required",
        ),
        (
            lambda report: report["host_refine"]["product_link_oracle"]["product_link"].update(
                emitted_buffer_sha256="6" * 64
            ),
            "refine product-link oracle",
        ),
        (lambda report: report["browser"].pop("csp_inline_blocked"), "strict-CSP"),
        (
            lambda report: report["browser"]["refine"].update(buffer_sha256=["4" * 64]),
            "buffer hashes",
        ),
        (
            lambda report: report["browser"]["refine"].update(wire_bytes=100_000),
            "wire byte counts",
        ),
        (
            lambda report: report["browser"]["refine"]["semantics"].update(visible=224_999),
            "semantics must match",
        ),
        (
            lambda report: report["browser"]["refine"].update(binning="javascript-fallback"),
            "labels must match",
        ),
        (
            lambda report: report["browser"]["refine"].update(transition_mode="reduced-motion"),
            "normal product transition",
        ),
        (
            lambda report: report["browser"]["refine"].update(facts_cache_delta=0),
            "intentional facts-only",
        ),
        (
            lambda report: report["browser"].update(requests=["density_view", "density_view"]),
            "exactly one",
        ),
        (
            lambda report: report["browser"]["view_transform"].update(
                applied_matches_requested=False
            ),
            "in-domain x zoom/pan",
        ),
        (
            lambda report: report["browser"]["refined_pixels"].update(sha256="1" * 64),
            "must differ",
        ),
    ],
)
def test_report_contract_rejects_spoofed_or_incomplete_evidence(mutation, message: str) -> None:
    report = _report()
    mutation(report)
    assert any(message in error for error in verify.validate(report))


@pytest.mark.parametrize(
    "path",
    [
        ("source", "bytes"),
        ("payload", "bytes"),
        ("limits", "source_ratio"),
        ("process_tree", "peak_rss_bytes"),
        ("host_refine", "reply_bytes"),
    ],
)
def test_report_contract_fails_closed_on_malformed_numeric_types(path) -> None:
    report = _report()
    report[path[0]][path[1]] = "100000"
    assert verify.validate(report)


def test_authority_is_impossible_off_main() -> None:
    with pytest.raises(ValueError, match="refs/heads/main"):
        bench._authority_guard(
            100_000_000,
            True,
            {
                "GITHUB_REF": "refs/pull/876/merge",
                "GITHUB_EVENT_NAME": "workflow_dispatch",
                "XYG_DENSITY_100M_AUTHORITY": "1",
            },
        )


def test_harness_rejects_noncanonical_point_count() -> None:
    with pytest.raises(ValueError, match="canonical 250k, 1M, or 100M"):
        bench._authority_guard(2_000_000, False, {})


def test_authority_requires_explicit_main_workflow_capability() -> None:
    environment = {
        "GITHUB_REF": "refs/heads/main",
        "GITHUB_EVENT_NAME": "schedule",
        "XYG_DENSITY_100M_AUTHORITY": "1",
    }
    bench._authority_guard(100_000_000, True, environment)
    with pytest.raises(ValueError, match="require --authority"):
        bench._authority_guard(100_000_000, False, environment)


def test_report_authority_requires_exact_size_context_and_sha() -> None:
    report = _report()
    report["authority"] = True
    assert any("if and only if" in error for error in verify.validate(report))

    report["authority"] = False
    report["point_count"] = 100_000_000
    assert any("if and only if" in error for error in verify.validate(report))

    report["authority"] = True
    report["authority_context"] = {
        "github_ref": "refs/heads/main",
        "github_event_name": "schedule",
        "capability": True,
    }
    assert any("requires --sha" in error for error in verify.validate(report))


def test_buffer_inventory_distinguishes_f64_from_offset_f32() -> None:
    spec = {
        "columns": [
            {"buf": 0, "dtype": "u8", "len": 4},
            {"buf": 1, "offset": 0.0, "len": 2},
            {"buf": 2, "dtype": "f64", "len": 1},
        ]
    }
    inventory = bench._buffer_inventory(spec, [b"1234", b"12345678", b"12345678"])
    assert inventory == {
        "classes": {
            "u8": {"buffers": 1, "bytes": 4},
            "offset-f32": {"buffers": 1, "bytes": 8},
            "f64": {"buffers": 1, "bytes": 8},
        },
        "buffer_count": 3,
        "bytes": 20,
        "canonical_f64_buffers": 1,
    }


def test_supervisor_timeout_reaps_worker_and_removes_temp_tree(tmp_path: Path) -> None:
    report_path = tmp_path / "timed-out.json"
    completed = subprocess.run(
        [
            sys.executable,
            str(ROOT / "benchmarks" / "bench_density_e2e.py"),
            "--points",
            "250000",
            "--chrome",
            sys.executable,
            "--timeout",
            "0.001",
            "--output",
            str(report_path),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )
    report = json.loads(report_path.read_text(encoding="utf-8"))

    assert completed.returncode == 1
    assert report["failure"] == "timeout"
    assert report["cleanup"]["orphan_pids_after_reap"] == []
    assert report["cleanup"]["temp_tree_removed"] is True


def test_supervisor_synthesizes_malformed_worker_report_and_removes_temp_tree(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class MalformedWorker:
        pid = 2_000_000_000
        returncode = 0

        def __init__(self, command, **_kwargs) -> None:
            config = json.loads(Path(command[-1]).read_text(encoding="utf-8"))
            Path(config["result"]).write_text('{"status":', encoding="utf-8")

        def poll(self) -> int:
            return 0

        def communicate(self, timeout: int) -> tuple[str, str]:
            assert timeout == 10
            return "", ""

    monkeypatch.setattr(bench.subprocess, "Popen", MalformedWorker)
    temp_root = tmp_path / "owned-temp"
    temp_root.mkdir()
    output = tmp_path / "malformed.json"
    args = argparse.Namespace(
        points=250_000,
        authority=False,
        max_disk_gib=1,
        output=output,
        temp_root=temp_root,
        chunk_points=250_000,
        chrome=Path(sys.executable),
        timeout=30.0,
        max_rss_gib=4.0,
        payload_ceiling_bytes=4_194_304,
    )

    assert bench._supervise(args) == 1
    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["failure"].startswith("malformed_worker_report:")
    assert report["cleanup"]["temp_tree_removed"] is True
    assert list(temp_root.iterdir()) == []


def test_cli_rejects_source_sized_generation_chunk(tmp_path: Path) -> None:
    completed = subprocess.run(
        [
            sys.executable,
            str(ROOT / "benchmarks" / "bench_density_e2e.py"),
            "--points",
            "250000",
            "--chunk-points",
            "100000000",
            "--chrome",
            sys.executable,
            "--output",
            str(tmp_path / "must-not-run.json"),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )

    assert completed.returncode == 2
    assert "chunk must be between" in completed.stderr
    assert not (tmp_path / "must-not-run.json").exists()


@pytest.mark.skipif(sys.platform != "linux", reason="process-group cleanup evidence uses /proc")
def test_supervisor_cancellation_owns_browser_temp_and_reaps_descendants(
    tmp_path: Path,
) -> None:
    fake_chrome = tmp_path / "fake-chrome"
    fake_chrome.write_text(
        "#!/usr/bin/env python3\n"
        "import os, pathlib, subprocess, sys, time\n"
        "root=pathlib.Path(os.environ['TMPDIR'])\n"
        "(root/'browser-profile-ready').write_text('ready')\n"
        "subprocess.Popen([sys.executable,'-c','import time; time.sleep(60)'])\n"
        "time.sleep(60)\n",
        encoding="utf-8",
    )
    fake_chrome.chmod(0o755)
    temp_root = tmp_path / "owned-temp"
    temp_root.mkdir()
    report_path = tmp_path / "cancelled.json"
    process = subprocess.Popen(
        [
            sys.executable,
            str(ROOT / "benchmarks" / "bench_density_e2e.py"),
            "--points",
            "250000",
            "--chrome",
            str(fake_chrome),
            "--timeout",
            "30",
            "--temp-root",
            str(temp_root),
            "--output",
            str(report_path),
        ],
        cwd=ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline and not list(temp_root.rglob("browser-profile-ready")):
        time.sleep(0.05)
    assert list(temp_root.rglob("browser-profile-ready")), "fake browser never reached launch"

    process.terminate()
    process.communicate(timeout=20)
    report = json.loads(report_path.read_text(encoding="utf-8"))

    assert process.returncode == 1
    assert report["failure"] == "cancelled"
    assert report["cleanup"]["orphan_pids_after_reap"] == []
    assert report["cleanup"]["temp_tree_removed"] is True
    assert list(temp_root.iterdir()) == []
