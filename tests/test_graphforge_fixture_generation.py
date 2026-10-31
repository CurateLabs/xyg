"""Synthetic property-base regeneration owns its Arrow files and manifest row."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("existing_manifest", [False, True])
def test_property_producer_restores_files_and_manifest(tmp_path, existing_manifest):
    pytest.importorskip("pyarrow")
    spec = importlib.util.spec_from_file_location(
        "ipc_fixtures", ROOT / "scripts" / "gen_graphforge_ipc_fixtures.py"
    )
    producer = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(producer)
    results = tmp_path / "results"
    manifest = {"bases": {"cyclic": {"nodes": "core-nodes"}}, "fixtures": {"pagerank": {}}}
    if existing_manifest:
        results.mkdir()
        (results / "manifest.json").write_text(json.dumps(manifest))
    producer.property_graph(results)
    actual = json.loads((results / "manifest.json").read_text())
    base = actual["bases"].pop("property")
    assert actual == (manifest if existing_manifest else {"bases": {}})
    assert base == {
        "nodes": "base-property-nodes",
        "edges": "base-property-edges",
        "generation": "0190a000-0000-7000-8000-000000000006",
    }
    for key in ("nodes", "edges"):
        name = f"{base[key]}.arrow"
        assert (results / name).read_bytes() == (
            ROOT / "tests/fixtures/graphforge/results" / name
        ).read_bytes()
    first = {path.name: path.read_bytes() for path in results.iterdir()}
    producer.property_graph(results)
    assert {path.name: path.read_bytes() for path in results.iterdir()} == first
