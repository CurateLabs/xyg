"""Packaged WASM assets: a missing or stale artifact must fail early and name itself (#1005)."""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from scripts import verify_wasm_assets as gate

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "scripts" / "verify_wasm_assets.py"
WASM = gate.WASM_MAGIC + b"fixture-module-bytes"
CLASSIC_WORKER = "(()=>{/* classic worker */})();"


def _make_root(tmp_path: Path) -> Path:
    """A synthetic checkout holding only what the verifier reads, plus valid assets."""
    root = tmp_path / "checkout"
    (root / "spec" / "wasm").mkdir(parents=True)
    shutil.copy2(REPO / "spec" / "wasm" / "abi.json", root / "spec" / "wasm" / "abi.json")
    abi = json.loads((root / "spec" / "wasm" / "abi.json").read_text(encoding="utf-8"))
    digest = hashlib.sha256(WASM).hexdigest()
    meta = {
        "schema_version": 1,
        "artifact": "xyg-wasm.wasm",
        "sha256": digest,
        "bytes": len(WASM),
        "abi_version": abi["abi_version"],
        "scene_version": abi["scene_version"],
        "painter_version": abi["painter_version"],
    }
    inline = (
        f'globalThis.__xygInlineWasm={{sha256:"{digest}",base64:"AA==",'
        f"classicWorkerSource:{json.dumps(CLASSIC_WORKER)}}};\n"
    )
    for location in gate.LOCATIONS:
        directory = root / location
        directory.mkdir(parents=True)
        (directory / "xyg-wasm.wasm").write_bytes(WASM)
        (directory / "xyg-wasm-inline.js").write_text(inline, encoding="utf-8")
        (directory / "xyg-wasm.manifest.json").write_text(json.dumps(meta), encoding="utf-8")
        (directory / "wasm-worker.js").write_text("worker", encoding="utf-8")
    (root / "packages/xy-client/dist/wasm-inline-worker.js").write_text(
        CLASSIC_WORKER, encoding="utf-8"
    )
    return root


def _cli(root: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-I", str(SCRIPT), "--root", str(root)],
        capture_output=True,
        text=True,
        check=False,
    )


def test_complete_assets_are_accepted(tmp_path: Path) -> None:
    root = _make_root(tmp_path)
    assert gate.verify(root) == []
    assert _cli(root).returncode == 0


def test_clean_checkout_fails_early_with_one_actionable_diagnostic(tmp_path: Path) -> None:
    """The #1005 state: generated assets are absent (not committed, §33)."""
    root = tmp_path / "clean"
    (root / "spec" / "wasm").mkdir(parents=True)
    shutil.copy2(REPO / "spec" / "wasm" / "abi.json", root / "spec" / "wasm" / "abi.json")

    result = _cli(root)

    assert result.returncode == 1
    assert result.stdout == ""
    for location in gate.LOCATIONS:
        assert f"{location}: missing xyg-wasm.wasm" in result.stderr
    assert "node js/build.mjs && npm run build:wasm" in result.stderr
    assert "wasm-assets" in result.stderr
    assert "Traceback" not in result.stderr


@pytest.mark.parametrize("location", gate.LOCATIONS)
@pytest.mark.parametrize("name", [*gate.PACKAGED, *gate.CLIENT])
def test_every_withheld_asset_is_named(tmp_path: Path, location: str, name: str) -> None:
    root = _make_root(tmp_path)
    (root / location / name).unlink()

    errors = gate.verify(root)

    assert len(errors) == 1
    assert errors[0].startswith(f"{location}: missing ") and name in errors[0]
    assert _cli(root).returncode == 1


def _rewrite_manifest(root: Path, location: str, **changes: object) -> None:
    path = root / location / "xyg-wasm.manifest.json"
    meta = json.loads(path.read_text(encoding="utf-8"))
    meta.update(changes)
    path.write_text(json.dumps(meta), encoding="utf-8")


@pytest.mark.parametrize("location", gate.LOCATIONS)
def test_stale_or_tampered_assets_are_rejected(tmp_path: Path, location: str) -> None:
    mutations = {
        "bytes differ from manifest": lambda r: (r / location / "xyg-wasm.wasm").write_bytes(
            gate.WASM_MAGIC + b"older-build"
        ),
        "stale ABI": lambda r: _rewrite_manifest(r, location, abi_version=1),
        "stale scene": lambda r: _rewrite_manifest(r, location, scene_version=1),
        "stale painter": lambda r: _rewrite_manifest(r, location, painter_version=1),
        "inline copy is another module": lambda r: (r / location / "xyg-wasm-inline.js").write_text(
            f'globalThis.__xygInlineWasm={{sha256:"{"0" * 64}",base64:"AA==",'
            f"classicWorkerSource:{json.dumps(CLASSIC_WORKER)}}};\n",
            encoding="utf-8",
        ),
        "not a wasm module": lambda r: (r / location / "xyg-wasm.wasm").write_bytes(b"<html>"),
    }
    for label, mutate in mutations.items():
        root = _make_root(tmp_path / label.replace(" ", "-"))
        mutate(root)
        assert gate.verify(root), label
        assert _cli(root).returncode == 1, label


def test_stale_classic_worker_and_diverged_copies_are_rejected(tmp_path: Path) -> None:
    root = _make_root(tmp_path / "worker")
    (root / "packages/xy-client/dist/wasm-inline-worker.js").write_text("changed", encoding="utf-8")
    assert any("stale classic worker" in error for error in gate.verify(root))

    root = _make_root(tmp_path / "diverged")
    (root / "python/xyg/static/xyg-wasm-inline.js").write_text(
        (root / "python/xyg/static/xyg-wasm-inline.js").read_text(encoding="utf-8") + "\n",
        encoding="utf-8",
    )
    assert any("differs between the two packaged locations" in e for e in gate.verify(root))
