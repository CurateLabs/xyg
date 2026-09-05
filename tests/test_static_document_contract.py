from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "tests" / "fixtures" / "static_document_contract.json"


def test_static_document_contract_is_complete_and_bounded() -> None:
    document = json.loads(CONTRACT.read_text(encoding="utf-8"))
    assert document["version"] == 1
    statuses = set(document["statuses"])
    assert statuses == {"RETAIN", "BROWSER_RETAIN", "FAIL_CLOSED"}
    journeys = document["journeys"]
    assert {row["surface"] for row in journeys} == {
        "figure_chart",
        "batch",
        "facets",
        "pyplot",
    }
    assert len({(row["surface"], row["route"]) for row in journeys}) == len(journeys)
    for row in journeys:
        assert row["status"] in statuses
        if row["status"] == "FAIL_CLOSED":
            assert row["reason"]
        else:
            assert row["reason"] is None
    assert {(row["surface"], row["route"]): (row["status"], row["reason"]) for row in journeys}[
        ("pyplot", "native_hexbin_group_budget")
    ] == (
        "FAIL_CLOSED",
        "XYG_SCENE_UNSUPPORTED_PUBLIC_LOD",
    )
