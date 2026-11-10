"""Desktop cohort and CI contracts that also run without the optional PNG oracle."""

from __future__ import annotations

import gzip
import hashlib
import io
import json
import os
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest
from scripts.install_vscode_graph_notebook import (
    application_payload,
    checked_artifact,
    installed_payloads,
)
from scripts.verify_ci_workflow import validate_workflow

ROOT = Path(__file__).resolve().parents[1]


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


@pytest.mark.parametrize("good_last", [True, False])
def test_duplicate_extension_ids_cannot_overwrite_an_unverified_directory(
    tmp_path, monkeypatch, good_last
):
    extensions = tmp_path / "extensions"
    downloads = tmp_path / "downloads"
    extensions.mkdir()
    downloads.mkdir()
    manifest = json.dumps({"publisher": "test", "name": "pinned", "version": "1.0"}).encode()
    bad = extensions / "first-unverified"
    good = extensions / "later-verified"
    bad.mkdir()
    (bad / "package.json").write_bytes(manifest)
    (bad / "unverified.js").write_text("throw Error('must not load')")
    good.mkdir()
    (good / "package.json").write_bytes(manifest)
    (good / ".vsixmanifest").write_bytes(b"manifest")
    archive = downloads / "test.pinned-1.0.vsix"
    with zipfile.ZipFile(archive, "w") as file:
        file.writestr("extension/package.json", manifest)
        file.writestr("extension.vsixmanifest", b"manifest")
    files = {
        "package.json": hashlib.sha256(
            json.dumps(json.loads(manifest), sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest(),
        ".vsixmanifest": hashlib.sha256(b"manifest").hexdigest(),
    }
    row = {
        "id": "test.pinned",
        "version": "1.0",
        "sha256": hashlib.sha256(archive.read_bytes()).hexdigest(),
        "payloadFiles": 2,
        "payloadSha256": hashlib.sha256(
            json.dumps(files, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest(),
    }
    original_iterdir = Path.iterdir
    monkeypatch.setattr(
        Path,
        "iterdir",
        lambda path: (
            iter((bad, good) if good_last else (good, bad))
            if path == extensions
            else original_iterdir(path)
        ),
    )
    with pytest.raises(ValueError, match="duplicate installed extension ID"):
        installed_payloads({"extensions": [row]}, extensions, downloads)


@pytest.mark.parametrize(
    "mutation", ["changed", "missing", "extra_file", "extra_directory", "execute", "link"]
)
def test_complete_application_payload_rejects_unpinned_resources(tmp_path, mutation):
    root = tmp_path / "application"
    resource = root / "resources/main.js"
    resource.parent.mkdir(parents=True)
    resource.write_bytes(b"original")
    resource.chmod(0o644)
    entries = {
        "resources": {"kind": "directory"},
        "resources/main.js": {
            "kind": "file",
            "bytes": 8,
            "sha256": hashlib.sha256(b"original").hexdigest(),
            "executable": False,
        },
    }
    digest = hashlib.sha256(
        json.dumps(entries, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    lock = {"payloadEntries": 2, "payloadSha256": digest}
    assert application_payload(lock, root) == {"entries": entries, "entriesSha256": digest}
    if mutation == "changed":
        resource.write_bytes(b"modified")
    elif mutation == "missing":
        resource.unlink()
    elif mutation == "extra_file":
        (root / "extra").write_bytes(b"unverified")
    elif mutation == "extra_directory":
        (root / "extra").mkdir()
    elif mutation == "execute":
        resource.chmod(0o755)
    else:
        (root / "link").symlink_to(resource)
    with pytest.raises(ValueError, match="installed application"):
        application_payload(lock, root)


def test_optional_png_oracle_does_not_block_cohort_or_weaken_required_verifier():
    script = r"""
import runpy,sys
class MissingPillow:
    def find_spec(self, fullname, path=None, target=None):
        if fullname == "PIL" or fullname.startswith("PIL."):
            raise ModuleNotFoundError("Pillow deliberately absent", name=fullname)
        return None
for name in list(sys.modules):
    if name == "PIL" or name.startswith("PIL."):
        del sys.modules[name]
sys.meta_path.insert(0, MissingPillow())
import pytest
runpy.run_path("tests/test_vscode_graph_notebook_cohort.py")
try:
    runpy.run_path("tests/test_vscode_graph_notebook_report.py")
except pytest.skip.Exception as error:
    assert "optional desktop PNG report oracle" in str(error), str(error)
else:
    raise AssertionError("image report tests did not admit optional dependency absence")
sys.path.insert(0, "scripts")
try:
    runpy.run_path("scripts/verify_vscode_graph_notebook_report.py", run_name="__main__")
except ModuleNotFoundError as error:
    assert error.name == "PIL" or error.name.startswith("PIL."), error
else:
    raise AssertionError("required desktop verifier silently accepted missing PNG oracle")
print("cohort imports; optional image tests skip; required verifier fails")
"""
    env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "required verifier fails" in result.stdout
