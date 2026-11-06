"""Fail closed on a pixel-only or helper-only graph notebook receipt."""

import copy
from pathlib import Path

import pytest
from scripts.classify_release_surface import classify
from scripts.verify_ci_workflow import validate_workflow
from scripts.verify_graph_notebook_report import verify


def green():
    return {
        "ok": True,
        "presentation": "Progressive property graph GraphForge result Company Person",
        "widgetCount": 2,
        "finalPointerVerified": True,
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


def test_notebook_changes_select_release_surfaces_and_smoke_is_required(tmp_path):
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
            "          node scripts/graph_notebook_progressive_smoke.mjs",
            "          echo skipped-notebook",
        )
    )
    assert any(
        "Progressive graph notebook journey" in error or "bounded real notebook" in error
        for error in validate_workflow(broken)
    )
