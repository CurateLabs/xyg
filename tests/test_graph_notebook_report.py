"""Fail closed on a pixel-only or helper-only graph notebook receipt."""

import copy
import gzip
import json
from pathlib import Path

import pytest
from scripts.classify_release_surface import classify
from scripts.verify_ci_workflow import validate_workflow
from scripts.verify_graph_notebook_report import geometry_expected, verify


def green():
    return {
        "geometryCallbacks": [
            {"identities": geometry_expected(mode)} for mode in ("box", "lasso", "box", "lasso")
        ],
        "geometry": [
            {
                "phase": phase,
                "expected": geometry_expected(mode),
                "mode": mode,
                "startStep": step,
                "endStep": step,
                "path": [[0, 0], [10, 10]]
                if mode == "box"
                else [[0, 0], [10, 0], [10, 10], [0, 10], [0, 0]],
                "pointer": [
                    {"kind": "pointerdown", "target": "CANVAS", "trusted": True, "x": 0, "y": 0}
                ]
                + [
                    {"kind": "pointermove", "target": "CANVAS", "trusted": True, "x": x, "y": y}
                    for x, y in (
                        [(10, 10)] * 8
                        if mode == "box"
                        else [(10, 0), (10, 10), (0, 10), (0, 0)] * 4
                    )
                ]
                + [
                    {
                        "kind": "pointerup",
                        "target": "CANVAS",
                        "trusted": True,
                        "x": 10 if mode == "box" else 0,
                        "y": 10 if mode == "box" else 0,
                    }
                ],
                "picture": {
                    "colors": 3,
                    "sha256": "a" * 64,
                    "edgeInk": 100 if mode == "box" else 10,
                },
            }
            for phase, mode, step in (
                ("progressive", "box", 9),
                ("progressive", "lasso", 17),
                ("complete", "box", 300),
                ("complete", "lasso", 300),
            )
        ],
        "ok": True,
        "presentation": "Progressive property graph GraphForge result Company Person",
        "widgetCount": 2,
        "finalPointerVerified": True,
        "finalPointer": {"before": 2, "after": 3, "id": "node-0", "expectedId": "node-0"},
        "kernel": {
            "native": {"abi": 399, "sha256": "c" * 64},
            "otherClicks": 0,
            "clicks": [{}, {}],
            "hovers": 1,
            "views": 1,
        },
        "expectedNativeHash": "c" * 64,
        "initialPicture": {"colors": 3, "sha256": "a" * 64, "step": "9"},
        "dimensions": {"colors": 3, "sha256": "b" * 64},
        "external": [],
        "kernelVerified": True,
        "disposed": True,
        "pageErrors": [],
        "frames": [{"step": str(step), "width": 900, "height": 420} for step in (1, 9, 300)],
        "events": {
            "actions": [{"kind": kind, "step": "9"} for kind in ("keydown", "wheel")],
            "events": [
                {"kind": kind, "detail": {"total": 1}} for kind in ("click", "hover", "select")
            ],
        },
    }


@pytest.mark.parametrize(
    "field,value",
    [
        ("frames", []),
        ("kernelVerified", False),
        ("disposed", False),
        ("pageErrors", ["failed"]),
        ("events", {}),
    ],
)
def test_receipt_rejects_missing_proof(field, value):
    report = green()
    assert not verify(report)
    report[field] = value
    assert verify(report)


def test_completed_only_input_is_not_unfinished_layout_proof():
    report = copy.deepcopy(green())
    for action in report["events"]["actions"]:
        action["step"] = "300"
    assert verify(report)


@pytest.mark.parametrize(
    "command",
    [
        "node scripts/graph_notebook_progressive_smoke.mjs",
        "node --test js/test/graph-host-transport.test.mjs",
    ],
)
def test_notebook_changes_select_release_surfaces_and_smoke_is_required(tmp_path, command):
    for path in (
        "tests/notebook_graph_progressive.ipynb",
        "scripts/graph_notebook_progressive_smoke.mjs",
        "python/xyg/_graph_widget.py",
    ):
        assert classify([path])
    workflow = Path(".github/workflows/ci.yml").read_text()
    broken = tmp_path / "ci.yml"
    broken.write_text(
        workflow.replace(
            "          " + command,
            "          echo skipped-notebook",
        )
    )
    assert any(
        "Progressive graph notebook journey" in error or "bounded real notebook" in error
        for error in validate_workflow(broken)
    )


def test_earlier_clicks_cannot_satisfy_final_pointer_proof():
    report = green()
    report["kernel"]["clicks"] = [{}, {}, {}]
    report["finalPointer"] = {"before": 3, "after": 3, "id": "node-0", "expectedId": "node-0"}
    assert any("after baseline" in error for error in verify(report))


def uuid_journey():
    report = green()
    requested = ["01000000-0000-0000-0000-000000000001", "02000000-0000-0000-0000-000000000001"]
    report["uuidSelection"] = {
        "requested": requested,
        "identities": [
            {"kind": kind, "uuid": value}
            for kind, value in zip(("node", "edge"), requested, strict=True)
        ],
    }
    report["kernel"]["clicks"][0]["graphforge"] = report["uuidSelection"]["identities"][:1]
    for event in report["events"]["events"]:
        if event["kind"] == "select":
            event["detail"]["total"] = 2
    return report


def test_uuid_selection_requires_both_requested_kinds_and_view_delivery():
    assert not verify(uuid_journey())


@pytest.mark.parametrize("total", [0, 1, 3, True, 2.0, "2"])
def test_uuid_selection_rejects_wrong_or_untyped_view_cardinality(total):
    report = uuid_journey()
    report["events"]["events"][-1]["detail"]["total"] = total
    assert any("exactly 2" in error for error in verify(report))


@pytest.mark.parametrize("mutation", ["duplicate", "wrong_identity", "wrong_kind", "missing"])
def test_uuid_selection_rejects_unbound_identity_request(mutation):
    report = uuid_journey()
    if mutation == "duplicate":
        report["uuidSelection"]["requested"][1] = report["uuidSelection"]["requested"][0]
    elif mutation == "wrong_identity":
        report["uuidSelection"]["identities"][1]["uuid"] = "03000000-0000-0000-0000-000000000001"
    elif mutation == "wrong_kind":
        report["uuidSelection"]["identities"][1]["kind"] = "node"
    else:
        del report["uuidSelection"]
    assert verify(report)


def test_legacy_row_selection_report_still_uses_original_contract():
    report = green()
    assert not verify(report)
    report["events"]["events"][-1]["detail"]["total"] = 2
    assert verify(report)


def test_retained_legacy_capture_does_not_claim_geometry_proof():
    path = Path("spec/performance/graph-widget-pr1100-repair-2026-11-06/notebook.json")
    assert any(
        "geometric selection proof" in error for error in verify(json.loads(path.read_text()))
    )


@pytest.mark.parametrize(
    "name", ["notebook-report-initial", "notebook-report", "notebook-report-final"]
)
def test_prior_identity_captures_do_not_claim_complete_uuid_request_proof(name):
    path = Path("spec/performance/graph-notebook-identity-2026-11-06") / f"{name}.json.gz"
    report = json.loads(gzip.decompress(path.read_bytes()))
    assert any("requires its UUID selection request" in error for error in verify(report))


@pytest.mark.parametrize(
    "mutation",
    [
        "wrong_uuid",
        "wrong_kind",
        "wrong_row",
        "missing",
        "duplicate",
        "path",
        "terminal",
        "untrusted",
        "vertex",
        "unfinished_release",
    ],
)
def test_geometry_proof_rejects_same_count_wrong_identities_and_incomplete_paths(mutation):
    report = green()
    records = report["geometryCallbacks"][0]["identities"]
    if mutation == "wrong_uuid":
        records[0]["uuid"] = records[1]["uuid"]
    elif mutation == "wrong_kind":
        records[0]["kind"] = "edge"
    elif mutation == "wrong_row":
        records[0]["layers"] = [{"layer": 0, "result_id": "wrong", "row": 7}]
    elif mutation == "missing":
        records.pop()
    elif mutation == "duplicate":
        records[-1] = records[0]
    elif mutation == "path":
        report["geometry"][0]["pointer"].pop()
    elif mutation == "untrusted":
        report["geometry"][0]["pointer"][0]["trusted"] = False
    elif mutation == "vertex":
        report["geometry"][0]["pointer"][-1]["x"] = 99
    elif mutation == "unfinished_release":
        report["geometry"][0]["endStep"] = 300
    else:
        report["geometry"][0]["startStep"] = 300
    assert verify(report)


def test_geometry_requires_visible_edge_mask_change():
    report = green()
    report["geometry"][1]["picture"]["edgeInk"] = report["geometry"][0]["picture"]["edgeInk"]
    assert any("visible edge masks" in error for error in verify(report))
