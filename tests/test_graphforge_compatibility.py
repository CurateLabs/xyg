"""Exact Core declarations reject unqualified pairs and stale corpus evidence."""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest
from scripts.check_graphforge_compatibility import DECLARATION, ROOT, check_compatibility


def declaration() -> dict:
    return json.loads(DECLARATION.read_text())


def test_exact_core_candidate_is_qualified_without_equal_rc_numbers() -> None:
    assert check_compatibility(
        declaration(), root=ROOT, core_version="0.6.0-rc.5", tag="xyg-v0.6.0-rc.1"
    ) == ["0.6.0-rc.5"]
    assert declaration()["selectedLaunchPairing"] is None


@pytest.mark.parametrize("version", ["0.6.0-rc.1", "0.6.0-rc.6", "0.6.0", "0.5.2"])
def test_other_core_candidates_require_their_own_qualification(version: str) -> None:
    with pytest.raises(ValueError, match="no qualified XYG result-schema declaration"):
        check_compatibility(declaration(), root=ROOT, core_version=version)


def test_changed_xyg_release_line_requires_qualification() -> None:
    with pytest.raises(ValueError, match="release line has no declared Core compatibility"):
        check_compatibility(declaration(), root=ROOT, tag="xyg-v0.7.0-rc.1")


def test_corpus_corruption_cannot_retain_a_qualified_declaration() -> None:
    altered = declaration()
    altered["supportedCoreResults"][0]["files"]["descriptors.json"]["sha256"] = "0" * 64
    with pytest.raises(ValueError, match="corpus integrity mismatch"):
        check_compatibility(altered, root=ROOT)


def test_missing_corpus_inventory_entry_fails() -> None:
    altered = declaration()
    del altered["supportedCoreResults"][0]["files"]["descriptors.json"]
    with pytest.raises(ValueError, match="file inventory differs"):
        check_compatibility(altered, root=ROOT)


def test_unrecognized_qualification_scope_fails() -> None:
    altered = declaration()
    altered["supportedCoreResults"][0]["qualification"] = "launch"
    with pytest.raises(ValueError, match="unsupported qualification scope"):
        check_compatibility(altered, root=ROOT)


def test_declaration_cannot_relabel_corpus_as_another_core_version() -> None:
    altered = copy.deepcopy(declaration())
    altered["supportedCoreResults"][0]["version"] = "0.6.0-rc.6"
    altered["supportedCoreResults"][0]["pythonVersion"] = "0.6.0rc6"
    for package in altered["supportedCoreResults"][0]["packages"]:
        package["version"] = "0.6.0-rc.6"
    with pytest.raises(ValueError, match="incomplete or mismatched native-produced corpus"):
        check_compatibility(altered, root=ROOT)


def test_corpus_must_be_inside_repository() -> None:
    altered = declaration()
    altered["supportedCoreResults"][0]["corpus"] = str(Path("/tmp"))
    with pytest.raises(ValueError, match="inside the repository"):
        check_compatibility(altered, root=ROOT)


@pytest.mark.parametrize("algorithm", ["bfs_depth", "dijkstra_cost"])
def test_scalar_paths_retain_identity_and_cost_without_inventing_paths(algorithm: str) -> None:
    import xyg

    result = (
        ROOT / "tests/fixtures/graphforge/core/0.6.0-rc.5/results" / f"{algorithm}.arrow"
    ).read_bytes()
    composition = xyg.compose_graphforge(layers=[{"result": result, "intent": "table"}])
    assert composition.ledger_version == 2
    assert composition.kind == "table"
    assert composition.table["columns"] == ["source_uuid", "target_uuid", "cost"]
    assert composition.table["kinds"] == ["uuid", "uuid", "float"]
    assert composition.table["rows"] == [
        [
            "01a16606-0da3-77db-a1f2-510b1f541190",
            "01a16606-0dd9-766d-bfd1-4fdb8bdb05a1",
            "1",
        ]
    ]
    with pytest.raises(xyg.GraphForgeCompositionError) as error:
        xyg.compose_graphforge(layers=[{"result": result, "intent": "graph"}])
    assert error.value.code == "GF_COMPOSE_INTENT_UNSUPPORTED"
