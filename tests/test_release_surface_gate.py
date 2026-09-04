"""Release-surface classifier and non-skippable aggregate contracts."""

from __future__ import annotations

from scripts.classify_release_surface import classify
from scripts.verify_release_surface_results import verify

REQUIRED_RESULTS = {
    "test": "success",
    "wasm_foundation": "success",
    "python_floor": "success",
    "browser_conformance": "success",
    "sdist": "success",
    "wheels": "success",
    "install_without_rust": "success",
    "authored_scene": "success",
}


def test_release_classifier_covers_every_contract_family() -> None:
    for path in (
        ".codspeed/config.json",
        "benchmarks/test_codspeed_kernels.py",
        "crates/xyg-core/src/lib.rs",
        "spec/abi/xyg.h",
        "spec/wasm/abi.json",
        "python/xyg/_figure.py",
        "python/xyg/_figure_export.py",
        "python/xyg/_payload.py",
        "python/xyg/_scene_v3.py",
        "packages/xy-node/src/figure.js",
        "js/src/49_wasm_density.ts",
        "hatch_build.py",
        "Makefile",
        "package.json",
        "pyproject.toml",
        ".github/workflows/ci.yml",
    ):
        assert classify([path]), path


def test_release_classifier_leaves_prose_only_change_optional() -> None:
    assert not classify(["docs/guide.md", "spec/design/example.md"])


def test_required_aggregate_rejects_skipped_release_job() -> None:
    results = {**REQUIRED_RESULTS, "wheels": "skipped"}
    assert verify(required=True, results=results) == [
        "release-surface job wheels must succeed, got 'skipped'"
    ]


def test_required_aggregate_accepts_complete_matrix() -> None:
    assert verify(required=True, results=REQUIRED_RESULTS) == []


def test_nonrelease_aggregate_accepts_expected_skips_but_not_failures() -> None:
    results = {
        **REQUIRED_RESULTS,
        "browser_conformance": "skipped",
        "sdist": "skipped",
        "wheels": "skipped",
        "install_without_rust": "skipped",
        "authored_scene": "skipped",
    }
    assert verify(required=False, results=results) == []
    results["sdist"] = "failure"
    assert verify(required=False, results=results) == [
        "optional release-surface job sdist failed with 'failure'"
    ]
