"""Fail closed on a pixel-only or helper-only graph notebook receipt."""

import copy
import gzip
import json
import subprocess
from pathlib import Path

import pytest
from scripts.classify_release_surface import classify
from scripts.verify_ci_workflow import _job_blocks, _named_step_blocks, validate_workflow
from scripts.verify_graph_notebook_report import ABI_VERSION, verify


def green():
    return {
        "ok": True,
        "presentation": "Progressive property graph GraphForge result Company Person",
        "widgetCount": 2,
        "finalPointerVerified": True,
        "finalPointer": {"before": 2, "after": 3, "id": "node-0", "expectedId": "node-0"},
        "kernel": {
            "native": {"abi": ABI_VERSION, "sha256": "c" * 64},
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


def test_retained_legacy_notebook_capture_still_passes():
    path = Path("spec/performance/graph-widget-pr1100-repair-2026-11-06/notebook.json")
    assert not verify(json.loads(path.read_text()), expected_abi=399)


@pytest.mark.parametrize(
    "name", ["notebook-report-initial", "notebook-report", "notebook-report-final"]
)
def test_prior_identity_captures_do_not_claim_complete_uuid_request_proof(name):
    path = Path("spec/performance/graph-notebook-identity-2026-11-06") / f"{name}.json.gz"
    report = json.loads(gzip.decompress(path.read_bytes()))
    assert any(
        "requires its UUID selection request" in error for error in verify(report, expected_abi=399)
    )


@pytest.mark.parametrize(
    "abi", [ABI_VERSION - 1, ABI_VERSION + 1, float(ABI_VERSION), str(ABI_VERSION), True]
)
def test_live_notebook_requires_exact_generated_native_abi(abi):
    report = green()
    report["kernel"]["native"]["abi"] = abi
    assert "selected native library evidence required" in verify(report)


def test_historical_native_abi_requires_an_explicit_artifact_contract():
    report = green()
    report["kernel"]["native"]["abi"] = 399
    assert verify(report)
    assert not verify(report, expected_abi=399)


def test_immutable_abi401_notebook_receipt_requires_explicit_historical_admission():
    path = Path(
        "spec/performance/pr1110-main-integration-2026-11-07/notebook-final-capture.json.gz"
    )
    report = json.loads(gzip.decompress(path.read_bytes()))
    assert report["kernel"]["native"]["abi"] == 401
    assert not verify(report, expected_abi=401)
    assert verify(report)  # Default and CLI require the generated current ABI.


def routed_journey():
    import base64
    import hashlib

    report = uuid_journey()
    document = base64.b64encode(b"bounded binary composition fixture").decode()
    identities = [
        {"kind": "edge", "uuid": f"02000000-0000-0000-0000-{i + 1:012d}", "index": i, "layers": []}
        for i in range(5)
    ]
    clicks = [
        {"trace": 0, "index": index, "graphforge": [identity]}
        for index, identity in zip((0, 1, 3, 5, 6), identities, strict=True)
    ]
    report["routedIdentity"] = {
        "fixture": {
            "composition": document,
            "nodeTrace": 1,
            "edgeTrace": 0,
            "edgeSources": [[0], [1], [2], [2], [2], [3], [4]],
            "expected": identities,
        },
        "clicks": clicks,
        "identityReleased": True,
    }
    report["routed"] = [
        {
            "source": source,
            "index": click["index"],
            "pointer": {"kind": "pointerdown", "step": "300"},
        }
        for source, click in enumerate(clicks)
    ]
    layered = {
        "kind": "node",
        "uuid": "01a0f3fd-23dd-76d3-87e7-d765a3665ef5",
        "index": 0,
        "layers": [{"layer": 0, "result_id": "notebook-rank", "row": 0}],
    }
    report["layeredIdentity"] = {
        "composition": document,
        "expected": layered,
        "click": {"graphforge": [layered]},
        "identityReleased": True,
    }
    report["layeredPointer"] = {"kind": "pointerdown", "step": "300"}
    report["uuidMasks"] = [
        {
            "trace": trace,
            "active": True,
            "count": count,
            "selected": [0],
            "values": [1] + [0] * (count - 1),
        }
        for trace, count in ((0, 7), (1, 5))
    ]
    report["nodeParity"] = {
        "ok": True,
        "inputSha256": "a" * 64,
        "nativeSha256": report["expectedNativeHash"],
        "documentSha256": hashlib.sha256(base64.b64decode(document)).hexdigest(),
        "layeredDocumentSha256": hashlib.sha256(base64.b64decode(document)).hexdigest(),
        "picks": [
            {"trace": c["trace"], "index": c["index"], "identity": c["graphforge"][0]}
            for c in clicks
        ],
        "layered": layered,
        "nodeMask": [0],
        "edgeMask": [0],
    }
    # Mutations must not change both callback and expected dictionaries by alias.
    return json.loads(json.dumps(report))


def test_current_routed_identity_journey_passes_and_legacy_requires_explicit_admission():
    assert not verify(routed_journey(), require_routed=True)
    assert verify(uuid_journey(), require_routed=True)
    assert not verify(uuid_journey())


@pytest.mark.parametrize(
    "field",
    ["routedIdentity", "routed", "layeredIdentity", "layeredPointer", "uuidMasks", "nodeParity"],
)
def test_current_journey_fails_closed_on_missing_identity_evidence(field):
    report = routed_journey()
    del report[field]
    assert verify(report, require_routed=True)


@pytest.mark.parametrize(
    "mutation",
    [
        "parallel",
        "loop",
        "row",
        "result_id",
        "node_parity",
        "binary",
        "mask",
        "mask_values",
        "retirement",
        "trusted",
        "typed_index",
    ],
)
def test_routed_identity_oracle_rejects_substantive_mutations(mutation):
    import base64

    report = routed_journey()
    if mutation == "parallel":
        report["routedIdentity"]["clicks"][1]["graphforge"] = report["routedIdentity"]["clicks"][0][
            "graphforge"
        ]
    elif mutation == "loop":
        del report["routedIdentity"]["clicks"][2]
    elif mutation in {"row", "result_id"}:
        report["layeredIdentity"]["click"]["graphforge"][0]["layers"][0][mutation] = 99
    elif mutation == "node_parity":
        report["nodeParity"]["picks"][0]["index"] = 4
    elif mutation == "binary":
        report["routedIdentity"]["fixture"]["composition"] = base64.b64encode(
            b"different document"
        ).decode()
    elif mutation == "mask":
        report["uuidMasks"][0]["selected"] = [1]
    elif mutation == "mask_values":
        report["uuidMasks"][1]["values"][1] = 1
    elif mutation == "retirement":
        report["layeredIdentity"]["identityReleased"] = False
    elif mutation == "trusted":
        report["routed"][0]["pointer"]["kind"] = "click"
    else:
        report["routedIdentity"]["clicks"][0]["graphforge"][0]["index"] = False
    assert verify(report, require_routed=True)


def test_normal_ci_cannot_drop_current_routed_identity_requirement(tmp_path):
    workflow = Path(".github/workflows/ci.yml").read_text()
    command = '.venv/bin/python scripts/verify_graph_notebook_report.py "$RUNNER_TEMP/graph-notebook.json" --require-routed'
    assert workflow.count(command) == 1
    broken = tmp_path / "ci.yml"
    broken.write_text(workflow.replace(command, command.removesuffix(" --require-routed")))
    assert any("bounded real notebook" in error for error in validate_workflow(broken))


def frontend_journey(kind):
    report = routed_journey()
    if kind == "notebook7":
        app, version, namespace, static, route = (
            "Jupyter Notebook",
            "7.5.8",
            "notebook",
            "/static/notebook",
            "/notebooks/graph.ipynb",
        )
    else:
        app, version, namespace, static, route = (
            "JupyterLab",
            "4.6.5",
            "lab",
            "/static/lab",
            "/lab/tree/graph.ipynb",
        )
    report["frontend"] = {
        "kind": kind,
        "appName": app,
        "version": version,
        "namespace": namespace,
        "staticUrl": static,
        "route": route,
        "staticRequests": [static + "/main.js"],
        "kernel": {"name": "Python 3 (ipykernel)", "status": "idle"},
    }
    return report


@pytest.mark.parametrize("kind", ["notebook7", "jupyterlab"])
def test_named_frontend_requires_real_configuration_route_and_assets(kind):
    assert not verify(frontend_journey(kind), require_routed=True, expected_frontend=kind)
    assert verify(routed_journey(), require_routed=True, expected_frontend=kind)
    other = "notebook7" if kind == "jupyterlab" else "jupyterlab"
    assert verify(frontend_journey(kind), require_routed=True, expected_frontend=other)


@pytest.mark.parametrize(
    "field,value",
    [
        ("kind", "jupyterlab"),
        ("appName", "JupyterLab"),
        ("version", "4.6.5"),
        ("version", 7),
        ("version", "7"),
        ("namespace", "lab"),
        ("staticUrl", "/static/lab"),
        ("route", "/lab/tree/graph.ipynb"),
        ("staticRequests", []),
        ("staticRequests", ["/static/lab/main.js"]),
    ],
)
def test_notebook7_report_cannot_relabel_another_frontend(field, value):
    report = frontend_journey("notebook7")
    report["frontend"][field] = value
    assert verify(report, require_routed=True, expected_frontend="notebook7")


@pytest.mark.parametrize(
    "command",
    [
        'uv venv --python .venv/bin/python "$RUNNER_TEMP/graph-notebook7-env"',
        'uv pip install --python "$RUNNER_TEMP/graph-notebook7-env/bin/python" notebook==7.5.8 jupyterlab==4.5.11 ipykernel==7.4.0 anywidget==0.11.0 numpy==2.4.6 pillow==13.0.0 pytest==9.2.0',
        'export XYG_GRAPH_JUPYTER="$RUNNER_TEMP/graph-notebook7-env/bin/jupyter-notebook"',
        "node scripts/graph_notebook_progressive_smoke.mjs --frontend notebook7",
        '.venv/bin/python scripts/verify_graph_notebook_report.py "$RUNNER_TEMP/graph-notebook7.json" --require-routed --frontend notebook7',
    ],
)
def test_notebook7_gate_cannot_skip_install_execution_or_real_frontend_verifier(tmp_path, command):
    workflow = Path(".github/workflows/ci.yml").read_text()
    steps = _named_step_blocks(_job_blocks(workflow)["test"])
    step = steps["Notebook 7 graph journey"]
    regions = steps["Notebook 7 graph regions"]
    assert step.count(command) == 1
    replacement = step.replace("          " + command, "          echo missing-notebook7")
    assert replacement != step
    broken = tmp_path / "ci.yml"
    broken.write_text(workflow.replace(step, replacement))
    assert (
        _named_step_blocks(_job_blocks(broken.read_text())["test"])["Notebook 7 graph regions"]
        == regions
    )
    assert any("Notebook7" in error for error in validate_workflow(broken))


@pytest.mark.parametrize("step_name", ["Notebook 7 graph journey", "Notebook 7 graph regions"])
def test_each_notebook7_step_requires_its_own_shared_launcher(tmp_path, step_name):
    workflow = Path(".github/workflows/ci.yml").read_text()
    steps = _named_step_blocks(_job_blocks(workflow)["test"])
    command = 'export XYG_GRAPH_JUPYTER="$RUNNER_TEMP/graph-notebook7-env/bin/jupyter-notebook"'
    assert all(
        steps[name].count(command) == 1
        for name in ("Notebook 7 graph journey", "Notebook 7 graph regions")
    )
    step = steps[step_name]
    broken = tmp_path / "ci.yml"
    broken.write_text(workflow.replace(step, step.replace(command, "echo missing-launcher")))
    errors = validate_workflow(broken)
    assert any(step_name in error for error in errors)
    other = (
        "Notebook 7 graph regions" if step_name.endswith("journey") else "Notebook 7 graph journey"
    )
    assert not any(other in error for error in errors)


@pytest.mark.parametrize(
    "kernel",
    [
        {"name": "No Kernel", "status": "idle"},
        {"name": "Python 3", "status": "busy"},
        {"name": "", "status": "idle"},
        {"name": None, "status": "idle"},
        {},
    ],
)
def test_frontend_cannot_submit_from_unselected_or_nonidle_kernel(kernel):
    report = frontend_journey("notebook7")
    report["frontend"]["kernel"] = kernel
    assert verify(report, require_routed=True, expected_frontend="notebook7")


def test_recorded_notebook764_runtime_failure_remains_unqualified():
    path = Path("spec/performance/graph-notebook7-2026-11-10/notebook764-failed.json.gz")
    report = json.loads(gzip.decompress(path.read_bytes()))
    assert report["frontend"]["version"] == "7.6.4"
    assert report["pageErrors"] == ["Cannot read properties of undefined (reading 'schema')"]
    assert "browser runtime errors" in verify(
        report, expected_abi=405, require_routed=True, expected_frontend="notebook7"
    )


def test_notebook_kernel_witness_retains_the_admitted_state_without_a_second_dom_read():
    result = subprocess.run(
        ["node", "--test", "js/test/graph-notebook-kernel-witness.test.mjs"],
        cwd=Path(__file__).resolve().parents[1],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
