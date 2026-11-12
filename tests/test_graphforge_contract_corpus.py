"""Core owns schema facts; XYG owns the qualified composition mapping (#936)."""

from __future__ import annotations

import csv
import hashlib
import json
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
CURRENT_BINDINGS = Path("spec/performance/filter-prefix-storage-2026-11-12/current-bindings.json")


def test_hash_bound_core_evidence_survives_windows_checkout(tmp_path: Path) -> None:
    """Exercise Git's real checkout conversion, including the hashed CJS generator."""
    paths = [
        Path("python/xyg/graphforge-compatibility.json"),
        Path("scripts/gen_graphforge_result_fixtures.cjs"),
        Path("scripts/gen_graphforge_rc7_result_fixtures.cjs"),
        Path("tests/fixtures/graphforge/results-0.6.0-rc.7/generation.json"),
        Path("tests/fixtures/graphforge/results-0.6.0-rc.5/generation.json"),
    ]
    for corpus, results in [
        ("core", "results"),
        ("core/0.6.0-rc.5", "results-0.6.0-rc.5"),
        ("core/0.6.0-rc.7", "results-0.6.0-rc.7"),
    ]:
        paths.extend(
            Path("tests/fixtures/graphforge") / corpus / name
            for name in ("contracts.tsv", "provenance.json")
        )
        paths.append(Path("tests/fixtures/graphforge") / results / "manifest.json")
    correction = CURRENT_BINDINGS
    current = json.loads((ROOT / correction).read_text())
    paths.extend(Path(path) for path in current["sourceSha256"])
    paths.extend(Path(path) for path in current["historicalBindings"])
    paths.extend(
        [
            correction,
            Path("spec/releases/core-rc7-generator-default-2026-11-06/original-generator.cjs"),
        ]
    )
    paths = list(dict.fromkeys(paths))
    original = {path: (ROOT / path).read_bytes() for path in paths}
    # An unpinned control must change, proving checkout filtering was exercised.
    original[Path("windows-default.txt")] = b"Windows default line endings\n"
    (tmp_path / ".gitattributes").write_bytes((ROOT / ".gitattributes").read_bytes())
    for path, payload in original.items():
        (tmp_path / path).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / path).write_bytes(payload)

    def git(*args: str) -> None:
        subprocess.run(
            ["git", "-C", str(tmp_path), *args], check=True, capture_output=True, text=True
        )

    git("init", "--quiet")
    git("config", "core.autocrlf", "true")
    git("config", "core.eol", "crlf")
    # Pinned upstream files may match their own ignore rules; reproduce the
    # actual tracked source set before exercising real checkout conversion.
    git("add", "--force", "--all")
    for path in original:
        (tmp_path / path).unlink()
    git("checkout-index", "--all", "--force")

    assert (tmp_path / "windows-default.txt").read_bytes() == b"Windows default line endings\r\n"
    changed = [str(path) for path in paths if (tmp_path / path).read_bytes() != original[path]]
    assert changed == [], f"Windows checkout changed hash-bound evidence bytes: {changed}"


@pytest.mark.parametrize(
    ("corpus_dir", "results_dir", "count"),
    [
        ("core", "results", 94),
        ("core/0.6.0-rc.5", "results-0.6.0-rc.5", 96),
        ("core/0.6.0-rc.7", "results-0.6.0-rc.7", 96),
    ],
)
def test_compatibility_declaration_is_grounded_in_real_core_evidence(
    corpus_dir: str, results_dir: str, count: int
) -> None:
    corpus_dir = ROOT / "tests/fixtures/graphforge" / corpus_dir
    provenance = json.loads((corpus_dir / "provenance.json").read_text())
    corpus = (corpus_dir / "contracts.tsv").read_bytes()
    manifest_bytes = (
        ROOT / "tests/fixtures/graphforge" / results_dir / "manifest.json"
    ).read_bytes()
    manifest = json.loads(manifest_bytes)
    declaration = json.loads((ROOT / "python/xyg/graphforge-compatibility.json").read_text())
    assert provenance["corpusSha256"] == hashlib.sha256(corpus).hexdigest()
    assert manifest["failures"] == {}
    assert declaration["supportedCoreVersions"] == ["0.5.2", "0.6.0-rc.5", "0.6.0-rc.7"]
    assert manifest["graphforgeVersion"] == provenance["coreVersion"]
    assert provenance["coreVersion"] in declaration["supportedCoreVersions"]
    assert {
        "coreVersion": provenance["coreVersion"],
        "coreSourceCommit": provenance["commit"],
        "contractCorpusSha256": provenance["corpusSha256"],
        "resultManifestSha256": hashlib.sha256(manifest_bytes).hexdigest(),
    } in declaration["evidence"]
    rows = list(csv.DictReader(corpus.decode().splitlines(), delimiter="\t"))
    actual = {(row["verb"], row["algorithm"], int(row["result_schema_version"])) for row in rows}
    expected = {
        (row["verb"], row["algorithm"], row["resultSchemaVersion"]) for row in manifest["contracts"]
    }
    assert actual == expected
    assert len(rows) == len(actual) == count
    assert declaration["algorithmSchemaVersions"] == sorted({version for _, _, version in actual})
    assert declaration["searchSchemaVersions"] == [1]


def test_ci_rebuilds_the_core_corpus_from_the_pinned_owner_sources() -> None:
    yaml = pytest.importorskip("yaml")

    workflow = yaml.safe_load((ROOT / ".github/workflows/ci.yml").read_text())
    steps = workflow["jobs"]["test"]["steps"]
    pin = next(step for step in steps if step.get("id") == "core_contract_pin")
    assert "core/0.6.0-rc.7/provenance.json" in pin["run"]
    checkout = next(
        step
        for step in steps
        if step.get("name") == "Fetch Core-owned schema and algorithm registries"
    )
    assert checkout["with"]["repository"] == "CurateLabs/graphforge"
    assert checkout["with"]["ref"] == "${{ steps.core_contract_pin.outputs.commit }}"
    assert checkout["with"]["path"] == "target/core-contracts"
    assert checkout["with"]["persist-credentials"] is False
    assert checkout["with"]["sparse-checkout-cone-mode"] is False
    assert checkout["with"]["sparse-checkout"].splitlines() == [
        "/Cargo.toml",
        "/crates/graphforge-core/src/algorithms.rs",
        "/crates/graphforge-api/src/invocation_descriptor.rs",
    ]
    verify = next(
        step
        for step in steps
        if step.get("name") == "Verify the pinned Core schema and descriptor corpus"
    )
    assert "sync_graphforge_contract_corpus.py --core-repo target/core-contracts" in verify["run"]
    assert "--output tests/fixtures/graphforge/core/0.6.0-rc.5" in verify["run"]
    assert "--output tests/fixtures/graphforge/core/0.6.0-rc.7" in verify["run"]
    assert "--write" not in verify["run"]


def test_rc5_fixtures_record_the_actual_published_binding_and_generation() -> None:
    results = ROOT / "tests/fixtures/graphforge/results-0.6.0-rc.5"
    generation = json.loads((results / "generation.json").read_text())
    provenance = json.loads(
        (ROOT / "tests/fixtures/graphforge/core/0.6.0-rc.5/provenance.json").read_text()
    )
    assert generation["coreVersion"] == provenance["coreVersion"] == "0.6.0-rc.5"
    assert generation["coreSourceCommit"] == provenance["commit"]
    assert (
        generation["manifestSha256"]
        == hashlib.sha256((results / "manifest.json").read_bytes()).hexdigest()
    )
    assert (
        generation["generatorSha256"]
        == hashlib.sha256((ROOT / generation["generator"]).read_bytes()).hexdigest()
    )
    assert generation["platform"] == "linux-x64-gnu"
    for package in generation["npmPackages"].values():
        assert package["version"] == "0.6.0-rc.5"
        assert package["integrity"].startswith("sha512-")


def test_rc7_artifact_provenance_and_every_generated_ipc_are_bound() -> None:
    import base64

    results = ROOT / "tests/fixtures/graphforge/results-0.6.0-rc.7"
    receipt = ROOT / "spec/releases/core-rc7-compatibility-2026-11-06"
    generation = json.loads((results / "generation.json").read_text())
    provenance = json.loads(
        (ROOT / "tests/fixtures/graphforge/core/0.6.0-rc.7/provenance.json").read_text()
    )
    # The original IPC producer is frozen; later CLI/default changes are bound
    # separately so historical fixtures never claim a different producing source.
    current = json.loads((ROOT / CURRENT_BINDINGS).read_text())
    for source, expected in current["sourceSha256"].items():
        assert hashlib.sha256((ROOT / source).read_bytes()).hexdigest() == expected
    for snapshot, expected in current["historicalBindings"].items():
        assert hashlib.sha256((ROOT / snapshot).read_bytes()).hexdigest() == expected
    assert current["manifestSha256"] == generation["manifestSha256"]
    assert current["originalProducerSha256"] == generation["generatorSha256"]
    producer = json.loads((receipt / "checks.json").read_text())
    assert (
        current["originalProducerSha256"]
        == producer["sourceSha256"]["scripts/gen_graphforge_rc7_result_fixtures.cjs"]
    )
    assert (
        hashlib.sha256((results / "generation.json").read_bytes()).hexdigest()
        == producer["sourceSha256"]["tests/fixtures/graphforge/results-0.6.0-rc.7/generation.json"]
    )
    assert generation["coreSourceCommit"] == provenance["commit"]
    assert generation["coreVersion"] == provenance["coreVersion"] == "0.6.0-rc.7"
    for key, path in [
        ("manifestSha256", results / "manifest.json"),
        (
            "generatorSha256",
            ROOT / "spec/releases/core-rc7-generator-default-2026-11-06/original-generator.cjs",
        ),
    ]:
        assert generation[key] == hashlib.sha256(path.read_bytes()).hexdigest()
    assert generation["files"] == {
        p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in results.glob("*.arrow")
    }
    assert len(generation["files"]) == 112
    for package, metadata in generation["npmPackages"].items():
        name = package.split("/")[-1]
        attestations = json.loads((receipt / f"{name}-attestations.json").read_text())
        attestation = next(
            a
            for a in attestations["attestations"]
            if a["predicateType"] == "https://slsa.dev/provenance/v1"
        )
        statement = json.loads(base64.b64decode(attestation["bundle"]["dsseEnvelope"]["payload"]))
        assert statement["subject"] == [
            {
                "name": f"pkg:npm/%40curatelabs/{name}@0.6.0-rc.7",
                "digest": {
                    "sha512": base64.b64decode(metadata["integrity"].removeprefix("sha512-")).hex()
                },
            }
        ]
        assert statement["predicate"]["buildDefinition"]["resolvedDependencies"] == [
            {
                "uri": "git+https://github.com/CurateLabs/graphforge@refs/tags/v0.6.0-rc.7",
                "digest": {"gitCommit": provenance["commit"]},
            }
        ]


def test_dense_navigation_successor_preserves_qualified_source_parents():
    current = json.loads(
        (ROOT / "spec/performance/browser-css-color-2026-11-08/current-bindings.json").read_text()
    )
    expected = {
        "spec/performance/temporal-dense-continuation-2026-11-08/current-bindings.json",
        "spec/performance/wasm-frozen-feature-ci-2026-11-08/current-bindings.json",
        "spec/performance/dense-native-navigation-union-2026-11-08/current-bindings.json",
        "spec/performance/dense-union-module-status-2026-11-08/current-bindings.json",
        "spec/performance/geo-hierarchy-temporal-remount-2026-11-08/current-bindings.json",
        "spec/performance/geo-hierarchy-application-remount-2026-11-08/current-bindings.json",
        "spec/performance/geo-hierarchy-held-reply-cleanup-2026-11-08/current-bindings.json",
    }
    assert len(current["parents"]) == 7
    assert {parent["path"] for parent in current["parents"]} == expected
    _assert_complete_parent_sources(current)


def test_combined_successor_preserves_both_complete_parent_bindings():
    current = json.loads(
        (
            ROOT / "spec/performance/active-m4-m7-integration-2026-11-08/current-bindings.json"
        ).read_text()
    )
    assert len(current["parents"]) == 2
    assert {p["path"] for p in current["parents"]} == {
        "spec/performance/browser-css-color-2026-11-08/current-bindings.json",
        "spec/performance/graph-public-scale-ownership-2026-11-08/current-bindings.json",
    }
    _assert_complete_parent_sources(current)


def _assert_complete_parent_sources(binding):
    import gzip

    successor = json.loads((ROOT / CURRENT_BINDINGS).read_text())
    for parent in binding["parents"]:
        raw = (ROOT / parent["path"]).read_bytes()
        assert hashlib.sha256(raw).hexdigest() == parent["sha256"]
        historical = json.loads(raw)
        source_hashes = historical.get("sourceSha256")
        if source_hashes is None:
            source_hashes = {
                path: record["sha256"] for path, record in historical["sources"].items()
            }
        for source, digest in source_hashes.items():
            if hashlib.sha256((ROOT / source).read_bytes()).hexdigest() != digest:
                archive = successor["predecessorSources"][parent["path"]][source]
                assert (
                    hashlib.sha256(gzip.decompress((ROOT / archive).read_bytes())).hexdigest()
                    == digest
                ), (parent["path"], source, digest)
        for source, digest in historical["historicalBindings"].items():
            if isinstance(digest, dict):
                digest = digest["sha256"]
            assert successor["historicalBindings"][source] == digest


def test_root_job_budget_eight_parents():
    current = json.loads(
        (
            ROOT / "spec/performance/graph-temporal-owner-charge-2026-11-08/current-bindings.json"
        ).read_text()
    )
    assert len(current["parents"]) == 8
    assert {p["path"] for p in current["parents"]} == {
        "spec/performance/geo-hierarchy-held-reply-cleanup-2026-11-08/current-bindings.json",
        "spec/performance/browser-css-color-2026-11-08/current-bindings.json",
        "spec/performance/temporal-dense-continuation-2026-11-08/current-bindings.json",
        "spec/performance/wasm-frozen-feature-ci-2026-11-08/current-bindings.json",
        "spec/performance/dense-native-navigation-union-2026-11-08/current-bindings.json",
        "spec/performance/geo-hierarchy-application-remount-2026-11-08/current-bindings.json",
        "spec/performance/dense-union-module-status-2026-11-08/current-bindings.json",
        "spec/performance/geo-hierarchy-temporal-remount-2026-11-08/current-bindings.json",
    }
    _assert_complete_parent_sources(current)


def test_final_fit_two_parents():
    current = json.loads(
        (
            ROOT / "spec/performance/module-space-recovery-2026-11-08/current-bindings.json"
        ).read_text()
    )
    assert len(current["parents"]) == 2
    assert {p["path"] for p in current["parents"]} == {
        "spec/performance/active-m4-m7-integration-2026-11-08/current-bindings.json",
        "spec/performance/graph-temporal-owner-charge-2026-11-08/current-bindings.json",
    }
    _assert_complete_parent_sources(current)


def test_current_union_preserves_all_qualified_root_and_fit_parents():
    current = json.loads(
        (
            ROOT / "spec/performance/current-large-graph-union-2026-11-09/current-bindings.json"
        ).read_text()
    )
    expected = {
        "spec/performance/active-m4-m7-integration-2026-11-08/current-bindings.json",
        "spec/performance/browser-css-color-2026-11-08/current-bindings.json",
        "spec/performance/ci-vendor-floor-discovery-2026-11-09/current-bindings.json",
        "spec/performance/dense-native-navigation-union-2026-11-08/current-bindings.json",
        "spec/performance/dense-union-module-status-2026-11-08/current-bindings.json",
        "spec/performance/five-temporal-drain-union-2026-11-09/current-bindings.json",
        "spec/performance/geo-five-temporal-successor-2026-11-08/current-bindings.json",
        "spec/performance/geo-hierarchy-application-remount-2026-11-08/current-bindings.json",
        "spec/performance/geo-hierarchy-held-reply-cleanup-2026-11-08/current-bindings.json",
        "spec/performance/geo-hierarchy-temporal-remount-2026-11-08/current-bindings.json",
        "spec/performance/graph-temporal-owner-charge-2026-11-08/current-bindings.json",
        "spec/performance/module-space-recovery-2026-11-08/current-bindings.json",
        "spec/performance/temporal-controller-view-2026-11-09/current-bindings.json",
        "spec/performance/temporal-dense-continuation-2026-11-08/current-bindings.json",
        "spec/performance/temporal-slice-clippy-2026-11-09/current-bindings.json",
        "spec/performance/wasm-frozen-feature-ci-2026-11-08/current-bindings.json",
    }
    assert len(current["parents"]) == 16
    assert {parent["path"] for parent in current["parents"]} == expected
    _assert_complete_parent_sources(current)


def test_native_python_ci_successor_retains_complete_published_union():
    parent_path = "spec/performance/current-large-graph-union-2026-11-09/current-bindings.json"
    parent = json.loads((ROOT / parent_path).read_text())
    current = json.loads(
        (ROOT / "spec/performance/native-python-ci-2026-11-09/current-bindings.json").read_text()
    )
    assert len(current["parents"]) == 17
    assert {p["path"] for p in current["parents"]} == {parent_path}.union(
        p["path"] for p in parent["parents"]
    )
    assert set(parent["sourceSha256"]) <= set(current["sourceSha256"])
    assert current["manifestSha256"] == parent["manifestSha256"]
    assert current["originalProducerSha256"] == parent["originalProducerSha256"]
    _assert_complete_parent_sources(current)


def test_frozen_browser_ci_successor_retains_native_ci_history():
    parent_path = "spec/performance/native-python-ci-2026-11-09/current-bindings.json"
    parent = json.loads((ROOT / parent_path).read_text())
    current = json.loads(
        (ROOT / "spec/performance/frozen-browser-ci-2026-11-09/current-bindings.json").read_text()
    )
    assert len(current["parents"]) == 18
    assert {p["path"] for p in current["parents"]} == {parent_path}.union(
        p["path"] for p in parent["parents"]
    )
    assert set(parent["sourceSha256"]) <= set(current["sourceSha256"])
    assert current["manifestSha256"] == parent["manifestSha256"]
    assert current["originalProducerSha256"] == parent["originalProducerSha256"]
    _assert_complete_parent_sources(current)


def test_procedural_graph_successor_retains_complete_frozen_ci_history():
    parent_path = "spec/performance/frozen-browser-ci-2026-11-09/current-bindings.json"
    parent = json.loads((ROOT / parent_path).read_text())
    current = json.loads(
        (
            ROOT / "spec/performance/graph-procedural-paint-2026-11-09/current-bindings.json"
        ).read_text()
    )
    assert len(current["parents"]) == 19
    assert {p["path"] for p in current["parents"]} == {parent_path}.union(
        p["path"] for p in parent["parents"]
    )
    assert set(parent["sourceSha256"]) <= set(current["sourceSha256"])
    assert current["manifestSha256"] == parent["manifestSha256"]
    assert current["originalProducerSha256"] == parent["originalProducerSha256"]
    _assert_complete_parent_sources(current)


def test_root_ci_thirteen_parent_contract_remains_complete():
    current = json.loads(
        (
            ROOT / "spec/performance/ci-vendor-floor-discovery-2026-11-09/current-bindings.json"
        ).read_text()
    )
    expected = {
        "spec/performance/browser-css-color-2026-11-08/current-bindings.json",
        "spec/performance/dense-native-navigation-union-2026-11-08/current-bindings.json",
        "spec/performance/dense-union-module-status-2026-11-08/current-bindings.json",
        "spec/performance/five-temporal-drain-union-2026-11-09/current-bindings.json",
        "spec/performance/geo-five-temporal-successor-2026-11-08/current-bindings.json",
        "spec/performance/geo-hierarchy-application-remount-2026-11-08/current-bindings.json",
        "spec/performance/geo-hierarchy-held-reply-cleanup-2026-11-08/current-bindings.json",
        "spec/performance/geo-hierarchy-temporal-remount-2026-11-08/current-bindings.json",
        "spec/performance/graph-temporal-owner-charge-2026-11-08/current-bindings.json",
        "spec/performance/temporal-controller-view-2026-11-09/current-bindings.json",
        "spec/performance/temporal-dense-continuation-2026-11-08/current-bindings.json",
        "spec/performance/temporal-slice-clippy-2026-11-09/current-bindings.json",
        "spec/performance/wasm-frozen-feature-ci-2026-11-08/current-bindings.json",
    }
    assert len(current["parents"]) == 13
    assert {parent["path"] for parent in current["parents"]} == expected
    _assert_complete_parent_sources(current)


def test_routed_notebook_successor_retains_complete_procedural_history():
    parent_path = "spec/performance/graph-procedural-paint-2026-11-09/current-bindings.json"
    parent = json.loads((ROOT / parent_path).read_text())
    current = json.loads(
        (
            ROOT
            / "spec/performance/graph-notebook-routed-identity-2026-11-09/current-bindings.json"
        ).read_text()
    )
    assert len(current["parents"]) == 20
    assert {p["path"] for p in current["parents"]} == {parent_path}.union(
        p["path"] for p in parent["parents"]
    )
    assert set(parent["sourceSha256"]) <= set(current["sourceSha256"])
    assert current["manifestSha256"] == parent["manifestSha256"]
    assert current["originalProducerSha256"] == parent["originalProducerSha256"]
    _assert_complete_parent_sources(current)


def test_notebook7_successor_retains_complete_routed_identity_history():
    parent_path = "spec/performance/graph-notebook-routed-identity-2026-11-09/current-bindings.json"
    parent = json.loads((ROOT / parent_path).read_text())
    current = json.loads(
        (ROOT / "spec/performance/graph-notebook7-2026-11-10/current-bindings.json").read_text()
    )
    assert len(current["parents"]) == 21
    assert {p["path"] for p in current["parents"]} == {parent_path}.union(
        p["path"] for p in parent["parents"]
    )
    assert set(parent["sourceSha256"]) <= set(current["sourceSha256"])
    assert current["manifestSha256"] == parent["manifestSha256"]
    assert current["originalProducerSha256"] == parent["originalProducerSha256"]
    _assert_complete_parent_sources(current)


def test_embedded_keyboard_successor_preserves_complete_notebook_history():
    parent_path = "spec/performance/graph-notebook7-2026-11-10/current-bindings.json"
    parent = json.loads((ROOT / parent_path).read_text())
    current = json.loads(
        (ROOT / "spec/performance/embedded-keyboard-2026-11-10/current-bindings.json").read_text()
    )
    assert len(current["parents"]) == 22
    assert {p["path"] for p in current["parents"]} == {parent_path}.union(
        p["path"] for p in parent["parents"]
    )
    assert set(parent["sourceSha256"]) <= set(current["sourceSha256"])
    assert current["manifestSha256"] == parent["manifestSha256"]
    assert current["originalProducerSha256"] == parent["originalProducerSha256"]
    _assert_complete_parent_sources(current)


def test_vscode_successor_preserves_complete_embedded_keyboard_history():
    parent_path = "spec/performance/embedded-keyboard-2026-11-10/current-bindings.json"
    parent = json.loads((ROOT / parent_path).read_text())
    current = json.loads(
        (
            ROOT / "spec/performance/graph-vscode-notebook-2026-11-10/current-bindings.json"
        ).read_text()
    )
    assert len(current["parents"]) == 23
    assert {p["path"] for p in current["parents"]} == {parent_path}.union(
        p["path"] for p in parent["parents"]
    )
    assert set(parent["sourceSha256"]) <= set(current["sourceSha256"])
    assert current["manifestSha256"] == parent["manifestSha256"]
    assert current["originalProducerSha256"] == parent["originalProducerSha256"]
    _assert_complete_parent_sources(current)


def test_complete_desktop_cohort_successor_preserves_original_qualification():
    parent_path = "spec/performance/graph-vscode-notebook-2026-11-10/current-bindings.json"
    parent = json.loads((ROOT / parent_path).read_text())
    current = json.loads(
        (
            ROOT
            / "spec/performance/graph-vscode-cohort-correction-2026-11-10/current-bindings.json"
        ).read_text()
    )
    assert len(current["parents"]) == 24
    assert {p["path"] for p in current["parents"]} == {parent_path}.union(
        p["path"] for p in parent["parents"]
    )
    assert set(parent["sourceSha256"]) <= set(current["sourceSha256"])
    assert current["manifestSha256"] == parent["manifestSha256"]
    assert current["originalProducerSha256"] == parent["originalProducerSha256"]
    _assert_complete_parent_sources(current)


def test_kernel_witness_successor_preserves_complete_keyboard_history():
    parent_path = "spec/performance/embedded-keyboard-2026-11-10/current-bindings.json"
    parent = json.loads((ROOT / parent_path).read_text())
    current = json.loads(
        (
            ROOT / "spec/performance/notebook-kernel-witness-2026-11-10/current-bindings.json"
        ).read_text()
    )
    assert len(current["parents"]) == 23
    assert {p["path"] for p in current["parents"]} == {parent_path}.union(
        p["path"] for p in parent["parents"]
    )
    assert set(parent["sourceSha256"]) <= set(current["sourceSha256"])
    assert current["manifestSha256"] == parent["manifestSha256"]
    assert current["originalProducerSha256"] == parent["originalProducerSha256"]
    _assert_complete_parent_sources(current)


def test_desktop_kernel_union_preserves_both_complete_parent_histories():
    parent_paths = {
        "spec/performance/graph-vscode-cohort-correction-2026-11-10/current-bindings.json",
        "spec/performance/notebook-kernel-witness-2026-11-10/current-bindings.json",
    }
    parents = [json.loads((ROOT / path).read_text()) for path in parent_paths]
    current = json.loads(
        (
            ROOT / "spec/performance/vscode-notebook-kernel-union-2026-11-10/current-bindings.json"
        ).read_text()
    )
    expected = parent_paths.union(
        *(set(p["path"] for p in parent["parents"]) for parent in parents)
    )
    assert len(current["parents"]) == 26
    assert {p["path"] for p in current["parents"]} == expected
    for parent in parents:
        assert set(parent["sourceSha256"]) <= set(current["sourceSha256"])
        assert current["manifestSha256"] == parent["manifestSha256"]
        assert current["originalProducerSha256"] == parent["originalProducerSha256"]
    _assert_complete_parent_sources(current)


def test_exact_reply_guard_successor_preserves_complete_kernel_witness_history():
    parent_path = "spec/performance/notebook-kernel-witness-2026-11-10/current-bindings.json"
    parent = json.loads((ROOT / parent_path).read_text())
    current = json.loads(
        (
            ROOT / "spec/performance/keyboard-exact-reply-guard-2026-11-10/current-bindings.json"
        ).read_text()
    )
    assert len(current["parents"]) == 24
    assert {p["path"] for p in current["parents"]} == {parent_path}.union(
        p["path"] for p in parent["parents"]
    )
    assert set(parent["sourceSha256"]) <= set(current["sourceSha256"])
    assert current["manifestSha256"] == parent["manifestSha256"]
    assert current["originalProducerSha256"] == parent["originalProducerSha256"]
    _assert_complete_parent_sources(current)


def test_desktop_exact_union_preserves_complete_reviewed_parent_histories():
    parent_paths = {
        "spec/performance/vscode-notebook-kernel-union-2026-11-10/current-bindings.json",
        "spec/performance/keyboard-exact-reply-guard-2026-11-10/current-bindings.json",
    }
    parents = [json.loads((ROOT / path).read_text()) for path in parent_paths]
    current = json.loads(
        (
            ROOT / "spec/performance/desktop-exact-reply-union-2026-11-10/current-bindings.json"
        ).read_text()
    )
    expected = parent_paths.union(
        *(set(p["path"] for p in parent["parents"]) for parent in parents)
    )
    assert len(current["parents"]) == 28
    assert {p["path"] for p in current["parents"]} == expected
    for parent in parents:
        assert set(parent["sourceSha256"]) <= set(current["sourceSha256"])
        assert current["manifestSha256"] == parent["manifestSha256"]
        assert current["originalProducerSha256"] == parent["originalProducerSha256"]
    _assert_complete_parent_sources(current)


def test_desktop_floor_successor_preserves_complete_reviewed_parent_history():
    parent_path = "spec/performance/desktop-exact-reply-union-2026-11-10/current-bindings.json"
    parent = json.loads((ROOT / parent_path).read_text())
    current = json.loads(
        (
            ROOT / "spec/performance/vscode-floor-collection-2026-11-10/current-bindings.json"
        ).read_text()
    )
    assert len(current["parents"]) == 29
    assert {p["path"] for p in current["parents"]} == {parent_path}.union(
        p["path"] for p in parent["parents"]
    )
    assert set(parent["sourceSha256"]) <= set(current["sourceSha256"])
    assert current["manifestSha256"] == parent["manifestSha256"]
    assert current["originalProducerSha256"] == parent["originalProducerSha256"]
    _assert_complete_parent_sources(current)


def test_notebook_regions_successor_preserves_complete_reviewed_parent_history():
    parent_path = "spec/performance/vscode-floor-collection-2026-11-10/current-bindings.json"
    parent = json.loads((ROOT / parent_path).read_text())
    current = json.loads(
        (
            ROOT / "spec/performance/graph-notebook-regions-2026-11-10/current-bindings.json"
        ).read_text()
    )
    assert len(current["parents"]) == 30
    assert {p["path"] for p in current["parents"]} == {parent_path}.union(
        p["path"] for p in parent["parents"]
    )
    assert set(parent["sourceSha256"]) <= set(current["sourceSha256"])
    assert current["manifestSha256"] == parent["manifestSha256"]
    assert current["originalProducerSha256"] == parent["originalProducerSha256"]
    _assert_complete_parent_sources(current)


def test_notebook_region_history_preserves_the_complete_candidate_and_review_chain():
    parent_path = "spec/performance/graph-notebook-regions-2026-11-10/current-bindings.json"
    parent = json.loads((ROOT / parent_path).read_text())
    current = json.loads(
        (
            ROOT / "spec/performance/graph-notebook-region-history-2026-11-10/current-bindings.json"
        ).read_text()
    )
    assert len(current["parents"]) == 31
    assert {p["path"] for p in current["parents"]} == {parent_path}.union(
        p["path"] for p in parent["parents"]
    )
    assert set(parent["sourceSha256"]) <= set(current["sourceSha256"])
    assert current["manifestSha256"] == parent["manifestSha256"]
    assert current["originalProducerSha256"] == parent["originalProducerSha256"]
    _assert_complete_parent_sources(current)


def test_notebook_camera_owner_preserves_the_complete_candidate_and_review_chain():
    parent_path = "spec/performance/graph-notebook-region-history-2026-11-10/current-bindings.json"
    parent = json.loads((ROOT / parent_path).read_text())
    current = json.loads(
        (
            ROOT / "spec/performance/graph-notebook-camera-owner-2026-11-10/current-bindings.json"
        ).read_text()
    )
    assert len(current["parents"]) == 32
    assert {p["path"] for p in current["parents"]} == {parent_path}.union(
        p["path"] for p in parent["parents"]
    )
    assert set(parent["sourceSha256"]) <= set(current["sourceSha256"])
    assert current["manifestSha256"] == parent["manifestSha256"]
    assert current["originalProducerSha256"] == parent["originalProducerSha256"]
    _assert_complete_parent_sources(current)


def test_linked_selection_owner_preserves_the_complete_candidate_and_review_chain():
    parent_path = "spec/performance/graph-notebook-camera-owner-2026-11-10/current-bindings.json"
    parent = json.loads((ROOT / parent_path).read_text())
    current = json.loads(
        (
            ROOT
            / "spec/performance/graph-linked-selection-ownership-2026-11-10/current-bindings.json"
        ).read_text()
    )
    assert len(current["parents"]) == 33
    assert {p["path"] for p in current["parents"]} == {parent_path}.union(
        p["path"] for p in parent["parents"]
    )
    assert set(parent["sourceSha256"]) <= set(current["sourceSha256"])
    assert current["manifestSha256"] == parent["manifestSha256"]
    assert current["originalProducerSha256"] == parent["originalProducerSha256"]
    _assert_complete_parent_sources(current)


def test_linked_mask_refresh_preserves_the_complete_candidate_and_review_chain():
    parent_path = (
        "spec/performance/graph-linked-selection-ownership-2026-11-10/current-bindings.json"
    )
    parent = json.loads((ROOT / parent_path).read_text())
    current = json.loads(
        (
            ROOT / "spec/performance/graph-linked-mask-refresh-2026-11-10/current-bindings.json"
        ).read_text()
    )
    assert len(current["parents"]) == 34
    assert {p["path"] for p in current["parents"]} == {parent_path}.union(
        p["path"] for p in parent["parents"]
    )
    assert set(parent["sourceSha256"]) <= set(current["sourceSha256"])
    assert current["manifestSha256"] == parent["manifestSha256"]
    assert current["originalProducerSha256"] == parent["originalProducerSha256"]
    _assert_complete_parent_sources(current)


def test_empty_clear_status_preserves_the_complete_candidate_and_review_chain():
    parent_path = "spec/performance/graph-linked-mask-refresh-2026-11-10/current-bindings.json"
    parent = json.loads((ROOT / parent_path).read_text())
    current = json.loads(
        (
            ROOT / "spec/performance/graph-empty-clear-status-2026-11-10/current-bindings.json"
        ).read_text()
    )
    assert len(current["parents"]) == 35
    assert {p["path"] for p in current["parents"]} == {parent_path}.union(
        p["path"] for p in parent["parents"]
    )
    assert set(parent["sourceSha256"]) <= set(current["sourceSha256"])
    assert current["manifestSha256"] == parent["manifestSha256"]
    assert current["originalProducerSha256"] == parent["originalProducerSha256"]
    _assert_complete_parent_sources(current)


def test_notebook7_regions_preserve_the_complete_candidate_and_review_chain():
    parent_path = "spec/performance/graph-empty-clear-status-2026-11-10/current-bindings.json"
    parent = json.loads((ROOT / parent_path).read_text())
    current = json.loads(
        (
            ROOT / "spec/performance/graph-notebook7-regions-2026-11-10/current-bindings.json"
        ).read_text()
    )
    assert len(current["parents"]) == 36
    assert {p["path"] for p in current["parents"]} == {parent_path}.union(
        p["path"] for p in parent["parents"]
    )
    assert set(parent["sourceSha256"]) <= set(current["sourceSha256"])
    assert current["manifestSha256"] == parent["manifestSha256"]
    assert current["originalProducerSha256"] == parent["originalProducerSha256"]
    _assert_complete_parent_sources(current)


def test_desktop_regions_preserve_the_complete_candidate_and_review_chain():
    parent_path = "spec/performance/graph-notebook7-regions-2026-11-10/current-bindings.json"
    parent = json.loads((ROOT / parent_path).read_text())
    current = json.loads(
        (
            ROOT / "spec/performance/graph-vscode-regions-2026-11-10/current-bindings.json"
        ).read_text()
    )
    assert len(current["parents"]) == 37
    assert {p["path"] for p in current["parents"]} == {parent_path}.union(
        p["path"] for p in parent["parents"]
    )
    assert set(parent["sourceSha256"]) <= set(current["sourceSha256"])
    assert current["manifestSha256"] == parent["manifestSha256"]
    assert current["originalProducerSha256"] == parent["originalProducerSha256"]
    _assert_complete_parent_sources(current)


def test_notebook_ci_repair_preserves_complete_reviewed_parent_history():
    parent_path = "spec/performance/graph-vscode-regions-2026-11-10/current-bindings.json"
    parent = json.loads((ROOT / parent_path).read_text())
    current = json.loads(
        (
            ROOT / "spec/performance/graph-notebook-ci-repair-2026-11-10/current-bindings.json"
        ).read_text()
    )
    assert len(current["parents"]) == 38
    assert {p["path"] for p in current["parents"]} == {parent_path}.union(
        p["path"] for p in parent["parents"]
    )
    assert set(parent["sourceSha256"]) <= set(current["sourceSha256"])
    assert current["manifestSha256"] == parent["manifestSha256"]
    assert current["originalProducerSha256"] == parent["originalProducerSha256"]
    _assert_complete_parent_sources(current)


def test_semantic_graph_session_preserves_complete_reviewed_parent_history():
    parent_path = "spec/performance/graph-notebook-ci-repair-2026-11-10/current-bindings.json"
    parent = json.loads((ROOT / parent_path).read_text())
    current = json.loads(
        (
            ROOT / "spec/performance/graph-semantic-session-2026-11-10/current-bindings.json"
        ).read_text()
    )
    assert len(current["parents"]) == 39
    assert {p["path"] for p in current["parents"]} == {parent_path}.union(
        p["path"] for p in parent["parents"]
    )
    assert set(parent["sourceSha256"]) <= set(current["sourceSha256"])
    assert current["manifestSha256"] == parent["manifestSha256"]
    assert current["originalProducerSha256"] == parent["originalProducerSha256"]
    _assert_complete_parent_sources(current)


def test_semantic_anchor_preserves_complete_source_qualification():
    parent_path = "spec/performance/graph-semantic-session-2026-11-10/current-bindings.json"
    parent = json.loads((ROOT / parent_path).read_text())
    current = json.loads(
        (
            ROOT / "spec/performance/graph-semantic-anchor-2026-11-10/current-bindings.json"
        ).read_text()
    )
    assert len(current["parents"]) == 40
    assert {p["path"] for p in current["parents"]} == {parent_path}.union(
        p["path"] for p in parent["parents"]
    )
    assert set(parent["sourceSha256"]) <= set(current["sourceSha256"])
    assert current["manifestSha256"] == parent["manifestSha256"]
    assert current["originalProducerSha256"] == parent["originalProducerSha256"]
    _assert_complete_parent_sources(current)


def test_native_admission_paint_preserves_complete_source_qualification():
    parent_path = "spec/performance/graph-semantic-anchor-2026-11-10/current-bindings.json"
    parent = json.loads((ROOT / parent_path).read_text())
    current = json.loads(
        (
            ROOT / "spec/performance/graph-native-admission-paint-2026-11-11/current-bindings.json"
        ).read_text()
    )
    assert len(current["parents"]) == 41
    assert {p["path"] for p in current["parents"]} == {parent_path}.union(
        p["path"] for p in parent["parents"]
    )
    assert set(parent["sourceSha256"]) <= set(current["sourceSha256"])
    assert current["manifestSha256"] == parent["manifestSha256"]
    assert current["originalProducerSha256"] == parent["originalProducerSha256"]
    _assert_complete_parent_sources(current)


def test_native_force_owner_preserves_complete_source_qualification():
    parent_path = "spec/performance/graph-native-admission-paint-2026-11-11/current-bindings.json"
    parent = json.loads((ROOT / parent_path).read_text())
    current = json.loads(
        (
            ROOT / "spec/performance/graph-native-force-owner-2026-11-11/current-bindings.json"
        ).read_text()
    )
    assert len(current["parents"]) == 42
    assert {p["path"] for p in current["parents"]} == {parent_path}.union(
        p["path"] for p in parent["parents"]
    )
    assert set(parent["sourceSha256"]) <= set(current["sourceSha256"])
    assert current["manifestSha256"] == parent["manifestSha256"]
    assert current["originalProducerSha256"] == parent["originalProducerSha256"]
    _assert_complete_parent_sources(current)


def test_pan_cancel_preserves_complete_source_qualification():
    parent_path = "spec/performance/graph-native-force-owner-2026-11-11/current-bindings.json"
    parent = json.loads((ROOT / parent_path).read_text())
    current = json.loads(
        (ROOT / "spec/performance/graph-pan-cancel-2026-11-11/current-bindings.json").read_text()
    )
    assert len(current["parents"]) == 43
    assert {p["path"] for p in current["parents"]} == {parent_path}.union(
        p["path"] for p in parent["parents"]
    )
    assert set(parent["sourceSha256"]) <= set(current["sourceSha256"])
    assert current["manifestSha256"] == parent["manifestSha256"]
    assert current["originalProducerSha256"] == parent["originalProducerSha256"]
    _assert_complete_parent_sources(current)


def test_python_session_isolation_preserves_complete_source_qualification():
    parent_path = "spec/performance/graph-pan-cancel-2026-11-11/current-bindings.json"
    parent = json.loads((ROOT / parent_path).read_text())
    current = json.loads(
        (
            ROOT
            / "spec/performance/graph-python-session-isolation-2026-11-11/current-bindings.json"
        ).read_text()
    )
    assert len(current["parents"]) == 44
    assert {p["path"] for p in current["parents"]} == {parent_path}.union(
        p["path"] for p in parent["parents"]
    )
    assert set(parent["sourceSha256"]) <= set(current["sourceSha256"])
    assert current["manifestSha256"] == parent["manifestSha256"]
    assert current["originalProducerSha256"] == parent["originalProducerSha256"]
    _assert_complete_parent_sources(current)


def test_tooltip_uuid_packing_preserves_complete_source_qualification():
    parent_path = "spec/performance/graph-python-session-isolation-2026-11-11/current-bindings.json"
    parent = json.loads((ROOT / parent_path).read_text())
    current = json.loads(
        (
            ROOT / "spec/performance/tooltip-uuid-packing-2026-11-11/current-bindings.json"
        ).read_text()
    )
    assert len(current["parents"]) == 45
    assert {p["path"] for p in current["parents"]} == {parent_path}.union(
        p["path"] for p in parent["parents"]
    )
    assert set(parent["sourceSha256"]) <= set(current["sourceSha256"])
    assert current["manifestSha256"] == parent["manifestSha256"]
    assert current["originalProducerSha256"] == parent["originalProducerSha256"]
    _assert_complete_parent_sources(current)


def test_visible_graph_region_input_preserves_complete_source_qualification():
    parent_path = "spec/performance/tooltip-uuid-packing-2026-11-11/current-bindings.json"
    parent = json.loads((ROOT / parent_path).read_text())
    current = json.loads(
        (
            ROOT / "spec/performance/graph-region-visible-input-2026-11-11/current-bindings.json"
        ).read_text()
    )
    assert len(current["parents"]) == 46
    assert {p["path"] for p in current["parents"]} == {parent_path}.union(
        p["path"] for p in parent["parents"]
    )
    assert set(parent["sourceSha256"]) <= set(current["sourceSha256"])
    assert current["manifestSha256"] == parent["manifestSha256"]
    assert current["originalProducerSha256"] == parent["originalProducerSha256"]
    _assert_complete_parent_sources(current)


def test_semantic_input_validation_preserves_complete_source_qualification():
    parent_path = "spec/performance/graph-region-visible-input-2026-11-11/current-bindings.json"
    parent = json.loads((ROOT / parent_path).read_text())
    current = json.loads(
        (
            ROOT / "spec/performance/graph-semantic-validation-2026-11-11/current-bindings.json"
        ).read_text()
    )
    assert len(current["parents"]) == 47
    assert {p["path"] for p in current["parents"]} == {parent_path}.union(
        p["path"] for p in parent["parents"]
    )
    assert set(parent["sourceSha256"]) <= set(current["sourceSha256"])
    assert current["manifestSha256"] == parent["manifestSha256"]
    assert current["originalProducerSha256"] == parent["originalProducerSha256"]
    _assert_complete_parent_sources(current)


def test_chunked_camera_publication_preserves_complete_source_qualification():
    parent_path = "spec/performance/graph-semantic-validation-2026-11-11/current-bindings.json"
    parent = json.loads((ROOT / parent_path).read_text())
    current = json.loads(
        (
            ROOT / "spec/performance/chunked-camera-publication-2026-11-11/current-bindings.json"
        ).read_text()
    )
    assert len(current["parents"]) == 48
    assert {p["path"] for p in current["parents"]} == {parent_path}.union(
        p["path"] for p in parent["parents"]
    )
    assert set(parent["sourceSha256"]) <= set(current["sourceSha256"])
    assert current["manifestSha256"] == parent["manifestSha256"]
    assert current["originalProducerSha256"] == parent["originalProducerSha256"]
    _assert_complete_parent_sources(current)


def test_uuid_tooltip_classification_preserves_complete_source_qualification():
    parent_path = "spec/performance/chunked-camera-publication-2026-11-11/current-bindings.json"
    parent = json.loads((ROOT / parent_path).read_text())
    current = json.loads(
        (
            ROOT / "spec/performance/tooltip-uuid-classification-2026-11-11/current-bindings.json"
        ).read_text()
    )
    assert len(current["parents"]) == 49
    assert {p["path"] for p in current["parents"]} == {parent_path}.union(
        p["path"] for p in parent["parents"]
    )
    assert set(parent["sourceSha256"]) <= set(current["sourceSha256"])
    assert current["manifestSha256"] == parent["manifestSha256"]
    assert current["originalProducerSha256"] == parent["originalProducerSha256"]
    _assert_complete_parent_sources(current)


def test_density_startup_recovery_preserves_complete_source_qualification():
    parent_path = "spec/performance/tooltip-uuid-classification-2026-11-11/current-bindings.json"
    parent = json.loads((ROOT / parent_path).read_text())
    current = json.loads(
        (
            ROOT / "spec/performance/density-startup-recovery-2026-11-11/current-bindings.json"
        ).read_text()
    )
    assert len(current["parents"]) == 50
    assert {p["path"] for p in current["parents"]} == {parent_path}.union(
        p["path"] for p in parent["parents"]
    )
    assert set(parent["sourceSha256"]) <= set(current["sourceSha256"])
    assert current["manifestSha256"] == parent["manifestSha256"]
    assert current["originalProducerSha256"] == parent["originalProducerSha256"]
    _assert_complete_parent_sources(current)


def test_graph_initial_context_recovery_preserves_complete_source_qualification():
    parent_path = "spec/performance/density-startup-recovery-2026-11-11/current-bindings.json"
    parent = json.loads((ROOT / parent_path).read_text())
    current = json.loads(
        (
            ROOT
            / "spec/performance/graph-initial-context-recovery-2026-11-11/current-bindings.json"
        ).read_text()
    )
    assert len(current["parents"]) == 51
    assert {p["path"] for p in current["parents"]} == {parent_path}.union(
        p["path"] for p in parent["parents"]
    )
    assert set(parent["sourceSha256"]) <= set(current["sourceSha256"])
    assert current["manifestSha256"] == parent["manifestSha256"]
    assert current["originalProducerSha256"] == parent["originalProducerSha256"]
    _assert_complete_parent_sources(current)


def test_graph_initial_deadline_preserves_complete_source_qualification():
    parent_path = "spec/performance/graph-initial-context-recovery-2026-11-11/current-bindings.json"
    parent = json.loads((ROOT / parent_path).read_text())
    current = json.loads(
        (
            ROOT / "spec/performance/graph-initial-deadline-2026-11-11/current-bindings.json"
        ).read_text()
    )
    assert len(current["parents"]) == 52
    assert {p["path"] for p in current["parents"]} == {parent_path}.union(
        p["path"] for p in parent["parents"]
    )
    assert set(parent["sourceSha256"]) <= set(current["sourceSha256"])
    assert current["manifestSha256"] == parent["manifestSha256"]
    assert current["originalProducerSha256"] == parent["originalProducerSha256"]
    _assert_complete_parent_sources(current)


def test_density_matrix_summary_preserves_complete_source_qualification():
    parent_path = "spec/performance/graph-initial-deadline-2026-11-11/current-bindings.json"
    parent = json.loads((ROOT / parent_path).read_text())
    current = json.loads(
        (
            ROOT / "spec/performance/density-matrix-summary-2026-11-11/current-bindings.json"
        ).read_text()
    )
    assert len(current["parents"]) == 53
    assert {p["path"] for p in current["parents"]} == {parent_path}.union(
        p["path"] for p in parent["parents"]
    )
    assert set(parent["sourceSha256"]) <= set(current["sourceSha256"])
    assert current["manifestSha256"] == parent["manifestSha256"]
    assert current["originalProducerSha256"] == parent["originalProducerSha256"]
    _assert_complete_parent_sources(current)


def test_filter_paged_cooperative_preserves_complete_source_qualification():
    parent_path = "spec/performance/density-matrix-summary-2026-11-11/current-bindings.json"
    parent = json.loads((ROOT / parent_path).read_text())
    current = json.loads(
        (
            ROOT / "spec/performance/filter-paged-cooperative-2026-11-11/current-bindings.json"
        ).read_text()
    )
    assert len(current["parents"]) == 54
    assert {p["path"] for p in current["parents"]} == {parent_path}.union(
        p["path"] for p in parent["parents"]
    )
    assert set(parent["sourceSha256"]) <= set(current["sourceSha256"])
    assert current["manifestSha256"] == parent["manifestSha256"]
    assert current["originalProducerSha256"] == parent["originalProducerSha256"]
    _assert_complete_parent_sources(current)


def test_filter_cooperative_status_preserves_complete_source_qualification():
    parent_path = "spec/performance/filter-paged-cooperative-2026-11-11/current-bindings.json"
    parent = json.loads((ROOT / parent_path).read_text())
    current = json.loads(
        (
            ROOT / "spec/performance/filter-cooperative-status-2026-11-11/current-bindings.json"
        ).read_text()
    )
    assert len(current["parents"]) == 55
    assert {p["path"] for p in current["parents"]} == {parent_path}.union(
        p["path"] for p in parent["parents"]
    )
    assert set(parent["sourceSha256"]) <= set(current["sourceSha256"])
    assert current["manifestSha256"] == parent["manifestSha256"]
    assert current["originalProducerSha256"] == parent["originalProducerSha256"]
    _assert_complete_parent_sources(current)


def test_filter_dossier_status_preserves_complete_source_qualification():
    parent_path = "spec/performance/filter-cooperative-status-2026-11-11/current-bindings.json"
    parent = json.loads((ROOT / parent_path).read_text())
    current = json.loads(
        (
            ROOT / "spec/performance/filter-dossier-status-2026-11-11/current-bindings.json"
        ).read_text()
    )
    assert len(current["parents"]) == 56
    assert {p["path"] for p in current["parents"]} == {parent_path}.union(
        p["path"] for p in parent["parents"]
    )
    assert set(parent["sourceSha256"]) <= set(current["sourceSha256"])
    assert current["manifestSha256"] == parent["manifestSha256"]
    assert current["originalProducerSha256"] == parent["originalProducerSha256"]
    _assert_complete_parent_sources(current)


def test_native_filter_callback_preserves_complete_source_qualification():
    parent_path = "spec/performance/filter-dossier-status-2026-11-11/current-bindings.json"
    parent = json.loads((ROOT / parent_path).read_text())
    current = json.loads(
        (
            ROOT / "spec/performance/filter-native-callback-2026-11-11/current-bindings.json"
        ).read_text()
    )
    assert len(current["parents"]) == 57
    assert {p["path"] for p in current["parents"]} == {parent_path}.union(
        p["path"] for p in parent["parents"]
    )
    assert set(parent["sourceSha256"]) <= set(current["sourceSha256"])
    assert current["manifestSha256"] == parent["manifestSha256"]
    assert current["originalProducerSha256"] == parent["originalProducerSha256"]
    _assert_complete_parent_sources(current)


def test_filter_benchmark_catalog_preserves_complete_source_qualification():
    parent_path = "spec/performance/filter-native-callback-2026-11-11/current-bindings.json"
    parent = json.loads((ROOT / parent_path).read_text())
    current = json.loads(
        (
            ROOT / "spec/performance/filter-benchmark-catalog-2026-11-11/current-bindings.json"
        ).read_text()
    )
    assert len(current["parents"]) == 58
    assert {p["path"] for p in current["parents"]} == {parent_path}.union(
        p["path"] for p in parent["parents"]
    )
    assert set(parent["sourceSha256"]) <= set(current["sourceSha256"])
    assert current["manifestSha256"] == parent["manifestSha256"]
    assert current["originalProducerSha256"] == parent["originalProducerSha256"]
    _assert_complete_parent_sources(current)


def test_filter_dashboard_baseline_preserves_complete_source_qualification():
    parent_path = "spec/performance/filter-benchmark-catalog-2026-11-11/current-bindings.json"
    parent = json.loads((ROOT / parent_path).read_text())
    current = json.loads(
        (
            ROOT / "spec/performance/filter-dashboard-baseline-2026-11-11/current-bindings.json"
        ).read_text()
    )
    assert len(current["parents"]) == 59
    assert {p["path"] for p in current["parents"]} == {parent_path}.union(
        p["path"] for p in parent["parents"]
    )
    assert set(parent["sourceSha256"]) <= set(current["sourceSha256"])
    assert current["manifestSha256"] == parent["manifestSha256"]
    assert current["originalProducerSha256"] == parent["originalProducerSha256"]
    _assert_complete_parent_sources(current)


def test_filter_emscripten_transport_preserves_complete_source_qualification():
    parent_path = "spec/performance/filter-dashboard-baseline-2026-11-11/current-bindings.json"
    parent = json.loads((ROOT / parent_path).read_text())
    current = json.loads(
        (
            ROOT / "spec/performance/filter-emscripten-transport-2026-11-12/current-bindings.json"
        ).read_text()
    )
    assert len(current["parents"]) == 60
    assert {p["path"] for p in current["parents"]} == {parent_path}.union(
        p["path"] for p in parent["parents"]
    )
    assert set(parent["sourceSha256"]) <= set(current["sourceSha256"])
    assert current["manifestSha256"] == parent["manifestSha256"]
    assert current["originalProducerSha256"] == parent["originalProducerSha256"]
    _assert_complete_parent_sources(current)


def test_filter_prefix_storage_preserves_complete_source_qualification():
    parent_path = "spec/performance/filter-emscripten-transport-2026-11-12/current-bindings.json"
    parent = json.loads((ROOT / parent_path).read_text())
    current = json.loads((ROOT / CURRENT_BINDINGS).read_text())
    assert len(current["parents"]) == 61
    assert {p["path"] for p in current["parents"]} == {parent_path}.union(
        p["path"] for p in parent["parents"]
    )
    assert set(parent["sourceSha256"]) <= set(current["sourceSha256"])
    assert current["manifestSha256"] == parent["manifestSha256"]
    assert current["originalProducerSha256"] == parent["originalProducerSha256"]
    _assert_complete_parent_sources(current)
