"""Adversarial admission of actual desktop notebook proof, not a pixel-only receipt."""

from __future__ import annotations

import copy
import gzip
import hashlib
import io
import json
from pathlib import Path

import pytest
from PIL import Image, ImageDraw
from scripts.graph_notebook_pixels import mark_witness
from scripts.install_vscode_graph_notebook import checked_artifact
from scripts.verify_ci_workflow import validate_workflow
from scripts.verify_vscode_graph_notebook_report import verify, verify_failure

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "spec/performance/graph-vscode-notebook-2026-11-10/qualification-fixtures.json"


@pytest.fixture(scope="module")
def recorded():
    records = json.loads(FIXTURES.read_text())
    bundles = {}
    for kind in ("normal", "failure"):
        bundles[kind] = {}
        for name, record in records[kind].items():
            archived = (ROOT / record["archive"]).read_bytes()
            assert hashlib.sha256(archived).hexdigest() == record["archiveSha256"]
            raw = gzip.decompress(archived)
            assert hashlib.sha256(raw).hexdigest() == record["sha256"]
            assert len(raw) == record["bytes"]
            bundles[kind][name] = raw
    return records, bundles


def admitted(records, bundle):
    return verify(
        bundle,
        expected_client=records["clientSha256"],
        expected_native=records["nativeSha256"],
        notebook_source=(ROOT / "tests/notebook_graph_progressive.ipynb").read_bytes(),
    )


def mutate(bundle, filename, path, value):
    changed = copy.copy(bundle)
    document = json.loads(bundle[filename])
    parent = document
    for key in path[:-1]:
        parent = parent[key]
    parent[path[-1]] = value
    changed[filename] = json.dumps(document).encode()
    return changed


def test_recorded_actual_desktop_and_intentional_failure_both_meet_their_contract(recorded):
    records, bundles = recorded
    assert not admitted(records, bundles["normal"])
    assert not verify_failure(bundles["failure"])
    assert admitted(records, bundles["failure"])
    assert verify_failure(bundles["normal"])


@pytest.mark.parametrize(
    "filename",
    [
        "report.json",
        "installation.json",
        "run-result.json",
        "cleanup.json",
        "graph.ipynb",
        "controller-complete.json",
        "served-widget-assets.json",
        "inspector-sources.json",
        "server-environment.json",
        "kernel-info.json",
        "identity-parity-input.json",
        "identity-parity.log",
        "initial.png",
        "final.png",
        "connected.png",
    ],
)
def test_a_report_alone_or_missing_sidecar_cannot_qualify(recorded, filename):
    records, bundles = recorded
    bundle = copy.copy(bundles["normal"])
    del bundle[filename]
    assert admitted(records, bundle)


@pytest.mark.parametrize(
    "filename,path,value",
    [
        ("report.json", ("frontend", "kind"), "jupyterlab"),
        ("report.json", ("frontend", "version"), "1.104.0"),
        ("report.json", ("frontend", "appHost"), "web"),
        ("report.json", ("frontend", "jupyterExtension"), "2026.7.0"),
        ("report.json", ("frontend", "normalGuiMode"), False),
        ("report.json", ("host", "executed"), []),
        ("report.json", ("host", "executed", 0, "execution", "success"), False),
        ("report.json", ("host", "executed", 0, "execution", "executionOrder"), 2),
        ("report.json", ("host", "executed", 1, "outputs"), []),
        ("report.json", ("frameTimeOrigin",), 0),
        ("report.json", ("clientSha256",), "f" * 64),
        ("report.json", ("expectedNativeHash",), "f" * 64),
        ("report.json", ("usedClientSources", "initial"), []),
        ("report.json", ("usedClientSources", "layered", "sha256"), "f" * 64),
        ("report.json", ("initialPicture", "sha256"), "f" * 64),
        ("report.json", ("dimensions", "width"), 1),
        ("report.json", ("uuidMasks", 0, "values"), [0] * 7),
        ("report.json", ("layeredIdentity", "identityReleased"), False),
        ("report.json", ("routedIdentity", "identityReleased"), False),
        ("report.json", ("markPixels",), []),
        ("report.json", ("connectedGeometry", "ranges", "x"), [0, 1]),
        ("report.json", ("networkScope",), "offline"),
        ("report.json", ("network",), []),
        ("report.json", ("network", 0, "origin"), "https://unapproved.invalid"),
        ("report.json", ("hostAssets",), []),
        ("report.json", ("pageErrors",), ["runtime failure"]),
        ("graph.ipynb", ("cells", 0, "source"), ["pass\n"]),
        ("controller-complete.json", ("ok",), False),
        ("run-result.json", ("attachmentExit",), 1),
        ("run-result.json", ("applicationExit",), False),
        ("run-result.json", ("serverKernels", 0, "execution_state"), "busy"),
        ("run-result.json", ("serverKernels", 0, "connections"), 1),
        ("cleanup.json", ("cookieRemoved",), False),
        ("cleanup.json", ("owned", 0, "terminated"), False),
        ("installation.json", ("lockSha256",), "f" * 64),
        ("installation.json", ("payloads", "ms-toolsai.jupyter", "filesSha256"), "f" * 64),
        ("served-widget-assets.json", (0, "installedBytesEqual"), False),
        ("server-environment.json", ("packages", "anywidget"), "0.0.0"),
        ("kernel-info.json", ("language_info", "version"), "3.10.0"),
        ("kernel-info.json", ("status",), "error"),
        ("identity-parity-input.json", ("uuidMasks",), []),
    ],
)
def test_desktop_verifier_rejects_substantive_missing_or_contradictory_evidence(
    recorded, filename, path, value
):
    records, bundles = recorded
    assert admitted(records, mutate(bundles["normal"], filename, path, value))


def test_byte_tampering_and_a_test_mode_app_cannot_qualify(recorded):
    records, bundles = recorded
    for filename in ("initial.png", "final.png", "identity-parity.log"):
        changed = copy.copy(bundles["normal"])
        changed[filename] = b"invalid artifact"
        assert admitted(records, changed)
    command = json.loads(bundles["normal"]["run-result.json"])["command"]
    assert admitted(
        records,
        mutate(
            bundles["normal"],
            "run-result.json",
            ("command",),
            [*command, "--extensionTestsPath=/fake"],
        ),
    )


@pytest.mark.parametrize(
    "filename,path,value",
    [
        ("failure.json", ("error",), "unrelated startup failure"),
        ("run-result.json", ("attachmentExit",), 0),
        ("run-result.json", ("applicationExit",), 1),
        ("run-result.json", ("intentionalFailureAfterCell",), None),
        ("cleanup.json", ("cookieRemoved",), False),
        ("cleanup.json", ("owned", 0, "terminated"), False),
    ],
)
def test_failed_host_only_passes_the_failure_contract_with_original_error_and_cleanup(
    recorded, filename, path, value
):
    _, bundles = recorded
    assert verify_failure(mutate(bundles["failure"], filename, path, value))


@pytest.mark.parametrize(
    "command",
    [
        'uv pip install --python "$RUNNER_TEMP/graph-notebook7-env/bin/python" nbclassic==1.3.3 ipywidgets==8.1.9 widgetsnbextension==4.0.16 jupyterlab_widgets==3.0.17',
        '.venv/bin/python scripts/install_vscode_graph_notebook.py --output "$RUNNER_TEMP/graph-vscode-cohort"',
        'export XYG_NATIVE_LIB="$GITHUB_WORKSPACE/target/release/libxyg_core.so"',
        'xvfb-run --auto-servernum --server-args="-screen 0 1280x900x24" .venv/bin/python scripts/graph_vscode_notebook_smoke.py --code "$RUNNER_TEMP/graph-vscode-cohort/application/VSCode-linux-x64/code" --extensions "$RUNNER_TEMP/graph-vscode-cohort/extensions" --server-python "$RUNNER_TEMP/graph-notebook7-env/bin/python" --output "$RUNNER_TEMP/graph-vscode"',
        '.venv/bin/python scripts/verify_vscode_graph_notebook_report.py "$RUNNER_TEMP/graph-vscode"',
    ],
)
def test_real_host_setup_execution_and_verifier_are_required_ci_commands(tmp_path, command):
    source = (ROOT / ".github/workflows/ci.yml").read_text()
    if command.startswith("export "):
        # Mutate only the named VS Code step, preserving other native gates.
        before, source = source.split("      - name: VS Code Jupyter graph journey", 1)
        source = (
            before
            + "      - name: VS Code Jupyter graph journey"
            + source.replace(command, "echo removed-native", 1)
        )
    else:
        assert source.count(command) == 1
        source = source.replace(command, "echo removed-vscode")
    path = tmp_path / "ci.yml"
    path.write_text(source)
    assert any("VS Code" in error for error in validate_workflow(path))


def test_http_gzip_is_transport_encoding_while_pins_cover_decoded_vsix(monkeypatch, tmp_path):
    raw = b"pinned VSIX bytes" * 128

    class Response(io.BytesIO):
        def __init__(self, data):
            super().__init__(data)
            self.headers = {"Content-Encoding": "gzip"}

    monkeypatch.setattr("urllib.request.urlopen", lambda *a, **kw: Response(gzip.compress(raw)))
    record = {
        "url": "https://example.invalid/package",
        "bytes": len(raw),
        "sha256": hashlib.sha256(raw).hexdigest(),
    }
    result = checked_artifact(record, tmp_path / "package.vsix", None)
    assert result["sha256"] == record["sha256"] and (tmp_path / "package.vsix").read_bytes() == raw
    with pytest.raises(ValueError, match="oversized"):
        checked_artifact({**record, "bytes": len(raw) - 1}, tmp_path / "oversized.vsix", None)


def test_a_corrupt_cached_artifact_is_refused_before_installation(tmp_path):
    cache = tmp_path / "cache"
    cache.mkdir()
    (cache / "package.vsix").write_bytes(b"tampered")
    with pytest.raises(ValueError, match="identity mismatch"):
        checked_artifact(
            {"url": "unused", "bytes": 8, "sha256": "0" * 64}, tmp_path / "package.vsix", cache
        )


def test_controls_and_legend_cannot_substitute_for_connected_mark_pixels(recorded):
    records, bundles = recorded
    bundle = copy.copy(bundles["normal"])
    report = json.loads(bundle["report.json"])
    with Image.open(io.BytesIO(bundle["connected.png"])) as source:
        image = source.convert("RGB")
    draw = ImageDraw.Draw(image)
    for witness in report["markPixels"]:
        x, y = (round(value) for value in witness["pixel"])
        background = tuple(int(value) for value in witness["background"])
        draw.rectangle((x - 6, y - 6, x + 6, y + 6), fill=background)
    output = io.BytesIO()
    image.save(output, format="PNG")
    bundle["connected.png"] = output.getvalue()
    report["connectedPicture"].update(
        sha256=hashlib.sha256(bundle["connected.png"]).hexdigest(),
        colors=len(image.getcolors(image.width * image.height)),
    )
    bundle["report.json"] = json.dumps(report).encode()
    assert admitted(records, bundle)
    with pytest.raises(ValueError, match="missing rendered mark"):
        mark_witness(
            bundle["connected.png"],
            report["routedIdentity"]["fixture"]["positions"],
            report["connectedGeometry"]["ranges"],
        )
    positions = copy.deepcopy(report["routedIdentity"]["fixture"]["positions"])
    ranges = report["connectedGeometry"]["ranges"]
    positions["x"] = [value + (ranges["x"][1] - ranges["x"][0]) * 0.15 for value in positions["x"]]
    with pytest.raises(ValueError, match="missing rendered mark"):
        mark_witness(bundles["normal"]["connected.png"], positions, ranges)
