"""Core owns schema facts; XYG owns the qualified composition mapping (#936)."""

from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize(
    ("corpus_dir", "results_dir", "count"),
    [("core", "results", 94), ("core/0.6.0-rc.5", "results-0.6.0-rc.5", 96)],
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
    assert declaration["supportedCoreVersions"] == ["0.5.2", "0.6.0-rc.5"]
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
