"""Adversarial region proof: identities, actual pixels, repeated execution and teardown."""

from __future__ import annotations

import copy
import gzip
import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

pytest.importorskip(
    "PIL.Image", reason="optional desktop PNG report oracle; actual CI verifier is required"
)
from scripts.verify_vscode_graph_regions_report import verify, verify_failure  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "spec/performance/graph-vscode-regions-2026-11-10/qualification-fixtures.json"


def test_trusted_pan_path_refuses_host_obstruction_including_between_endpoints():
    script = r"""
import assert from 'node:assert/strict';
import {visibleGraphRegionPanPath} from './scripts/graph_notebook_region_journey.mjs';
const box={left:378,top:361.75,width:824,height:338};
const canvas={getBoundingClientRect:()=>box,evaluate:fn=>fn(canvas)};
const blocker={tagName:'DIV'};
let hit=()=>canvas;
globalThis.document={elementFromPoint:(x,y)=>hit(x-box.left,y-box.top)};
const original={start:[618,253.5],end:[638,241.5]};
assert.deepEqual(await visibleGraphRegionPanPath(canvas),original);
// Match the hosted sidebar boundary: the former 75% path misses the canvas.
hit=(x,y)=>x<526?canvas:blocker;
const exposed=await visibleGraphRegionPanPath(canvas);
assert.ok(exposed&&exposed.start[0]<526&&exposed.end[0]<526);
assert.equal(exposed.end[0]-exposed.start[0],20);
assert.equal(exposed.end[1]-exposed.start[1],-12);
// Clear endpoints do not qualify a path whose middle is intercepted.
hit=(x,y)=>x>624&&x<632?blocker:canvas;
assert.notDeepEqual(await visibleGraphRegionPanPath(canvas),original);
hit=()=>blocker;
assert.equal(await visibleGraphRegionPanPath(canvas),null);
"""
    result = subprocess.run(
        ["node", "--input-type=module", "-e", script],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.fixture(scope="module")
def recorded():
    records = json.loads(FIXTURES.read_text())
    bundles = {}
    for kind in ("normal", "failure"):
        bundles[kind] = {}
        for name, pin in records[kind].items():
            archived = (ROOT / pin["archive"]).read_bytes()
            assert hashlib.sha256(archived).hexdigest() == pin["archiveSha256"]
            raw = gzip.decompress(archived)
            assert hashlib.sha256(raw).hexdigest() == pin["sha256"] and len(raw) == pin["bytes"]
            bundles[kind][name] = raw
    return records, bundles


def admitted(records, bundle):
    return verify(
        bundle,
        expected_client=records["clientSha256"],
        expected_native=records["nativeSha256"],
        notebook_source=(ROOT / "tests/notebook_graph_regions.ipynb").read_bytes(),
    )


def replace_document(bundle, name, path, value):
    result = copy.copy(bundle)
    document = json.loads(result[name])
    parent = document
    for key in path[:-1]:
        parent = parent[key]
    parent[path[-1]] = value
    result[name] = json.dumps(document).encode()
    return result


def synchronize_cell_reports(bundle):
    result = copy.copy(bundle)
    report = json.loads(result["report.json"])
    snapshots = [
        report["initial"],
        report["capacity"]["refused"],
        report["box"],
        report["lasso"],
        report["cameraBox"],
    ]
    index = 0
    for row in report["host"]["executed"]:
        if row["index"] != 1:
            continue
        found = False
        for items in row["outputs"]:
            for item in items:
                if item["data"].startswith("XYG graph region report"):
                    item["data"] = "XYG graph region report " + json.dumps(snapshots[index]) + "\n"
                    found = True
        assert found
        index += 1
    assert index == 5
    result["report.json"] = json.dumps(report).encode()
    return result


def test_actual_desktop_region_and_failure_cleanup_bundles_are_admitted(recorded):
    records, bundles = recorded
    assert not admitted(records, bundles["normal"])
    assert not verify_failure(bundles["failure"])


@pytest.mark.parametrize(
    ("filename", "path", "value"),
    [
        ("report.json", ["frontend", "kind"], "jupyterlab"),
        ("report.json", ["clientSha256"], "0" * 64),
        ("report.json", ["dpr"], True),
        ("report.json", ["usedClientSources"], []),
        ("report.json", ["trusted", 0, "trusted"], False),
        ("report.json", ["capacity", "after", "paintSha256"], "0" * 64),
        ("report.json", ["combinedHistory", "restored"], {}),
        ("report.json", ["host", "executed", 2, "execution", "executionOrder"], 2),
        ("run-result.json", ["regionsJourney"], False),
        ("run-result.json", ["applicationExit"], 1),
        ("cleanup.json", ["cookieRemoved"], False),
        ("installation.json", ["lockSha256"], "0" * 64),
        ("kernel-info.json", ["status"], "error"),
    ],
)
def test_mislabeled_or_stale_application_and_lifecycle_evidence_rejects(
    recorded, filename, path, value
):
    records, bundles = recorded
    assert admitted(records, replace_document(bundles["normal"], filename, path, value))


@pytest.mark.parametrize(
    ("path", "value"),
    [
        (["lasso", "selections", -1, "identities", 0, "uuid"], "0" * 32),
        (["lassoMasks", 0, "values"], []),
        (["box", "selections", -1, "identities", 0, "index"], 999),
        (["initial", "fixture", "x", 0], float("nan")),
        (["initial", "native_sha256"], "0" * 64),
        (["cameraBox", "report_sequence"], 1),
    ],
)
def test_resigned_cell_outputs_cannot_bypass_identity_and_count_oracles(recorded, path, value):
    records, bundles = recorded
    bundle = replace_document(bundles["normal"], "report.json", path, value)
    assert admitted(records, synchronize_cell_reports(bundle))


def test_resigned_static_workbench_image_cannot_qualify_as_visible_dimming(recorded):
    records, bundles = recorded
    bundle = copy.copy(bundles["normal"])
    bundle["box.png"] = bundle["before.png"]
    digest = hashlib.sha256(bundle["box.png"]).hexdigest()
    bundle = replace_document(bundle, "report.json", ["afterBox", "sha256"], digest)
    bundle = replace_document(bundle, "box-pixels.json", ["result", "sha256"], digest)
    assert admitted(records, bundle)


@pytest.mark.parametrize(
    "filename", ["box-paint.png", "before.png", "graph.ipynb", "inspector-sources.json"]
)
def test_missing_raw_witnesses_reject(recorded, filename):
    records, bundles = recorded
    bundle = copy.copy(bundles["normal"])
    del bundle[filename]
    assert admitted(records, bundle)


@pytest.mark.parametrize(
    ("filename", "path", "value"),
    [
        ("failure.json", ["error"], "different failure"),
        ("run-result.json", ["attachmentExit"], 0),
        ("cleanup.json", ["cookieRemoved"], False),
        ("failure-owner-cleanup.json", ["output"], "cleanup missing"),
    ],
)
def test_failure_cleanup_must_preserve_error_and_native_release(recorded, filename, path, value):
    _, bundles = recorded
    assert verify_failure(replace_document(bundles["failure"], filename, path, value))


def test_optimized_python_still_rejects_resigned_stale_execution(recorded, tmp_path):
    records, bundles = recorded
    bundle = replace_document(
        bundles["normal"], "report.json", ["host", "executed", 2, "execution", "executionOrder"], 2
    )
    p = tmp_path / "bundle.json"
    p.write_text(json.dumps({name: value.decode("latin1") for name, value in bundle.items()}))
    command = [
        sys.executable,
        "-O",
        "-c",
        "import json,sys; from pathlib import Path; from scripts.verify_vscode_graph_regions_report import verify; x=json.load(open(sys.argv[1])); errors=verify({k:v.encode('latin1') for k,v in x.items()},expected_client=sys.argv[2],expected_native=sys.argv[3],notebook_source=Path('tests/notebook_graph_regions.ipynb').read_bytes()); raise SystemExit(0 if errors else 1)",
        str(p),
        records["clientSha256"],
        records["nativeSha256"],
    ]
    result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize("resign_sidecar", [False, True])
def test_actual_native_cleanup_output_cannot_disagree_or_claim_failed_release(
    recorded, resign_sidecar
):
    _, bundles = recorded
    bundle = copy.copy(bundles["failure"])
    state = json.loads(bundle["extension-state.json"])
    replacement = 'XYG graph region cleanup {"owners": 0, "released": false}\n'
    changed = False
    for output in state["executed"][-1]["outputs"]:
        for item in output:
            if item["data"].startswith("XYG graph region cleanup"):
                item["data"] = replacement
                changed = True
    assert changed
    bundle["extension-state.json"] = json.dumps(state).encode()
    if resign_sidecar:
        bundle["failure-owner-cleanup.json"] = json.dumps({"output": replacement}).encode()
    assert verify_failure(bundle)
