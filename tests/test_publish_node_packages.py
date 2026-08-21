"""Retry and immutable-artifact contracts for the XYG npm release set."""

from __future__ import annotations

import importlib.util
import io
import json
import sys
import tarfile
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "scripts" / "publish_node_packages.py"


def _load():
    spec = importlib.util.spec_from_file_location("publish_node_packages", SCRIPT)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def _pack(path: Path, manifest: dict[str, object]) -> None:
    payload = (json.dumps(manifest) + "\n").encode()
    with tarfile.open(path, "w:gz") as archive:
        info = tarfile.TarInfo("package/package.json")
        info.size = len(payload)
        archive.addfile(info, io.BytesIO(payload))


def _release(tmp_path: Path, version: str = "1.2.3"):
    mod = _load()
    optionals = {name: version for name in mod.EXPECTED_NAMES if name != mod.FACADE}
    for index, name in enumerate(mod.EXPECTED_NAMES):
        manifest: dict[str, object] = {"name": name, "version": version}
        if name == mod.FACADE:
            manifest["optionalDependencies"] = optionals
        _pack(tmp_path / f"artifact-{index}.tgz", manifest)
    return mod


def test_load_release_requires_complete_aligned_set_and_facade_last(tmp_path: Path) -> None:
    mod = _release(tmp_path)
    artifacts = mod.load_release(tmp_path)
    assert [artifact.name for artifact in artifacts] == list(mod.EXPECTED_NAMES)
    assert artifacts[-1].name == mod.FACADE


def test_publish_retry_skips_only_identical_registry_bytes(tmp_path: Path, monkeypatch) -> None:
    mod = _release(tmp_path)
    artifacts = mod.load_release(tmp_path)
    published: list[str] = []
    monkeypatch.setattr(mod, "_registry_shasum", lambda spec: artifacts[0].shasum)
    monkeypatch.setattr(
        mod.subprocess,
        "run",
        lambda command, check: published.append(command[2]),
    )
    mod.publish_release([artifacts[0]])
    assert published == []

    monkeypatch.setattr(mod, "_registry_shasum", lambda spec: "0" * 40)
    with pytest.raises(RuntimeError, match="differs"):
        mod.publish_release([artifacts[0]])


def test_publish_processes_native_packages_before_facade(tmp_path: Path, monkeypatch) -> None:
    mod = _release(tmp_path)
    artifacts = mod.load_release(tmp_path)
    published: list[str] = []
    monkeypatch.setattr(mod, "_registry_shasum", lambda spec: None)
    monkeypatch.setattr(
        mod.subprocess,
        "run",
        lambda command, check: published.append(Path(command[2]).name),
    )
    mod.publish_release(artifacts)
    by_path = {artifact.path.name: artifact.name for artifact in artifacts}
    assert [by_path[name] for name in published] == list(mod.EXPECTED_NAMES)
