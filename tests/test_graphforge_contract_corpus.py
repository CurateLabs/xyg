"""Core owns schema facts; XYG owns the qualified composition mapping (#936)."""

from __future__ import annotations

import csv
import hashlib
import json
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def test_hash_bound_core_evidence_survives_windows_checkout(tmp_path: Path) -> None:
    """Exercise Git's real checkout conversion, including the hashed CJS generator."""
    paths = [
        Path("python/xyg/graphforge-compatibility.json"),
        Path("scripts/gen_graphforge_result_fixtures.cjs"),
        Path("tests/fixtures/graphforge/results-0.6.0-rc.5/generation.json"),
    ]
    for corpus, results in [("core", "results"), ("core/0.6.0-rc.5", "results-0.6.0-rc.5")]:
        paths.extend(
            Path("tests/fixtures/graphforge") / corpus / name
            for name in ("contracts.tsv", "provenance.json")
        )
        paths.append(Path("tests/fixtures/graphforge") / results / "manifest.json")
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
    git("add", "--all")
    for path in original:
        (tmp_path / path).unlink()
    git("checkout-index", "--all", "--force")

    assert (tmp_path / "windows-default.txt").read_bytes() == b"Windows default line endings\r\n"
    changed = [str(path) for path in paths if (tmp_path / path).read_bytes() != original[path]]
    assert changed == [], f"Windows checkout changed hash-bound evidence bytes: {changed}"


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
