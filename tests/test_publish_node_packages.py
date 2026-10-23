"""Retry and immutable-artifact contracts for the XYG npm release set."""

from __future__ import annotations

import hashlib
import importlib.util
import io
import json
import subprocess
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


def _pack(path: Path, manifest: dict[str, object], files: dict[str, bytes] | None = None) -> None:
    payload = (json.dumps(manifest) + "\n").encode()
    with tarfile.open(path, "w:gz") as archive:
        info = tarfile.TarInfo("package/package.json")
        info.size = len(payload)
        archive.addfile(info, io.BytesIO(payload))
        for name, content in (files or {}).items():
            info = tarfile.TarInfo(f"package/{name}")
            info.size = len(content)
            archive.addfile(info, io.BytesIO(content))


def _native(os_name: str, cpu: str) -> bytes:
    if os_name == "linux":
        payload = bytearray(64)
        payload[:6] = b"\x7fELF\x02\x01"
        payload[18:20] = {"x64": 62, "arm64": 183}[cpu].to_bytes(2, "little")
        return bytes(payload)
    if os_name == "darwin":
        return b"\xcf\xfa\xed\xfe" + {
            "x64": 0x01000007,
            "arm64": 0x0100000C,
        }[cpu].to_bytes(4, "little")
    payload = bytearray(80)
    payload[:2] = b"MZ"
    payload[0x3C:0x40] = (64).to_bytes(4, "little")
    payload[64:68] = b"PE\0\0"
    payload[68:70] = (0x8664).to_bytes(2, "little")
    return bytes(payload)


def _release(tmp_path: Path, version: str = "1.2.3"):
    mod = _load()
    optionals = {name: version for name in mod.NATIVE_NAMES}
    for index, name in enumerate(mod.EXPECTED_NAMES):
        manifest: dict[str, object] = {"name": name, "version": version}
        files = None
        if name == mod.FACADE:
            manifest["optionalDependencies"] = optionals
        elif name == mod.BROWSER:
            manifest.update({"type": "module", "exports": mod.EXPECTED_EXPORTS})
            files = {
                f"dist/{name}": b"\0asm\x01\0\0\0" if name.endswith(".wasm") else b"export {};"
                for name in mod.ASSETS
            }
            inventory = {
                "schemaVersion": 1,
                "package": mod.BROWSER,
                "packageVersion": version,
                "assets": {
                    name: {
                        "bytes": len(files[f"dist/{name}"]),
                        "sha256": hashlib.sha256(files[f"dist/{name}"]).hexdigest(),
                    }
                    for name in mod.ASSETS
                },
            }
            files["ASSET-MANIFEST.json"] = json.dumps(inventory).encode()
        else:
            platform_id = name.removeprefix(f"{mod.FACADE}-")
            library, os_name, cpu = mod.PLATFORM_LAYOUTS[platform_id]
            manifest.update({"os": [os_name], "cpu": [cpu]})
            files = {library: _native(os_name, cpu)}
        _pack(tmp_path / f"artifact-{index}.tgz", manifest, files)
    return mod


def test_load_release_requires_complete_aligned_set_and_facade_last(tmp_path: Path) -> None:
    mod = _release(tmp_path)
    artifacts = mod.load_release(tmp_path)
    assert [artifact.name for artifact in artifacts] == list(mod.EXPECTED_NAMES)
    assert artifacts[-1].name == mod.FACADE


def test_load_release_rejects_non_object_manifest(tmp_path: Path) -> None:
    path = tmp_path / "bad.tgz"
    payload = b"[]\n"
    with tarfile.open(path, "w:gz") as archive:
        info = tarfile.TarInfo("package/package.json")
        info.size = len(payload)
        archive.addfile(info, io.BytesIO(payload))
    with pytest.raises(ValueError, match="not a JSON object"):
        _load().load_release(tmp_path)


@pytest.mark.parametrize("corruption", ["missing-native", "wrong-metadata"])
def test_load_release_rejects_corrupt_native_archive(tmp_path: Path, corruption: str) -> None:
    mod = _release(tmp_path)
    platform_id = next(iter(mod.PLATFORM_LAYOUTS))
    package_name = f"{mod.FACADE}-{platform_id}"
    target = tmp_path / f"artifact-{mod.EXPECTED_NAMES.index(package_name)}.tgz"
    library, os_name, cpu = mod.PLATFORM_LAYOUTS[platform_id]
    manifest = {
        "name": f"{mod.FACADE}-{platform_id}",
        "version": "1.2.3",
        "os": ["linux"] if corruption == "wrong-metadata" else [os_name],
        "cpu": [cpu],
    }
    files = {} if corruption == "missing-native" else {library: _native(os_name, cpu)}
    _pack(target, manifest, files)
    with pytest.raises(ValueError, match=r"contain|os/cpu"):
        mod.load_release(tmp_path)


def test_publish_retry_skips_only_identical_registry_bytes(tmp_path: Path, monkeypatch) -> None:
    mod = _release(tmp_path)
    artifacts = mod.load_release(tmp_path)
    published: list[str] = []
    monkeypatch.setattr(
        mod,
        "_registry_dist",
        lambda spec: mod.RegistryDist(artifacts[0].shasum, artifacts[0].integrity),
    )
    monkeypatch.setattr(
        mod.subprocess,
        "run",
        lambda command, check, timeout: published.append(command[2]),
    )
    mod.publish_release([artifacts[0]])
    assert published == []

    monkeypatch.setattr(
        mod,
        "_registry_dist",
        lambda spec: mod.RegistryDist(artifacts[0].shasum, "sha512-wrong"),
    )
    with pytest.raises(RuntimeError, match="immutable registry mismatch"):
        mod.publish_release([artifacts[0]])


def test_publish_processes_native_packages_before_facade(tmp_path: Path, monkeypatch) -> None:
    mod = _release(tmp_path)
    artifacts = mod.load_release(tmp_path)
    published: list[str] = []
    monkeypatch.setattr(
        mod.subprocess,
        "run",
        lambda command, check, timeout: published.append(Path(command[2]).name),
    )
    by_spec = {f"{artifact.name}@{artifact.version}": artifact for artifact in artifacts}
    calls = {spec: 0 for spec in by_spec}

    def registry(spec):
        calls[spec] += 1
        if calls[spec] == 1:
            return None
        artifact = by_spec[spec]
        return mod.RegistryDist(artifact.shasum, artifact.integrity)

    monkeypatch.setattr(mod, "_registry_dist", registry)
    mod.publish_release(artifacts)
    by_path = {artifact.path.name: artifact.name for artifact in artifacts}
    assert [by_path[name] for name in published] == list(mod.EXPECTED_NAMES)


def test_registry_metadata_requires_both_hashes(monkeypatch) -> None:
    mod = _load()

    def run(*args, **kwargs):
        return subprocess.CompletedProcess(args[0], 0, '{"shasum":"abc"}\n', "")

    monkeypatch.setattr(mod.subprocess, "run", run)
    with pytest.raises(RuntimeError, match=r"SHA-512 dist\.integrity"):
        mod._registry_dist("@curatelabs/xyg-node@1.2.3")


def test_post_publish_visibility_failure_is_actionable(tmp_path: Path, monkeypatch) -> None:
    mod = _release(tmp_path)
    artifact = mod.load_release(tmp_path)[0]
    monkeypatch.setattr(mod, "REGISTRY_VERIFY_ATTEMPTS", 2)
    monkeypatch.setattr(mod, "REGISTRY_VERIFY_DELAY_S", 0)
    monkeypatch.setattr(mod, "_registry_dist", lambda spec: None)
    monkeypatch.setattr(mod.subprocess, "run", lambda *args, **kwargs: None)
    with pytest.raises(RuntimeError, match="retry the release to verify immutable bytes"):
        mod.publish_release([artifact])


def test_publish_timeout_fails_through_the_stable_cli_error(tmp_path: Path, monkeypatch) -> None:
    mod = _release(tmp_path)

    def timeout(command, **kwargs):
        assert kwargs["timeout"] == mod.NPM_TIMEOUT_S
        raise subprocess.TimeoutExpired(command, kwargs["timeout"])

    monkeypatch.setattr(mod.subprocess, "run", timeout)
    assert mod.main([str(tmp_path)]) == 1


def test_prereleases_publish_under_the_next_dist_tag(tmp_path: Path, monkeypatch) -> None:
    mod = _release(tmp_path)
    artifacts = mod.load_release(tmp_path)
    commands: list[list[str]] = []
    monkeypatch.setattr(
        mod.subprocess, "run", lambda command, check, timeout: commands.append(command)
    )
    published: set[str] = set()

    def registry(spec):
        if spec not in published:
            published.add(spec)
            return None
        artifact = next(a for a in artifacts if f"{a.name}@{a.version}" == spec)
        return mod.RegistryDist(artifact.shasum, artifact.integrity)

    monkeypatch.setattr(mod, "_registry_dist", registry)
    mod.publish_release(artifacts)
    for command, artifact in zip(commands, artifacts, strict=True):
        tagged = command[-2:] == ["--tag", "next"]
        assert tagged == ("-" in artifact.version), (artifact.version, command)
    assert mod._dist_tag("0.6.0-rc.1") == ["--tag", "next"]
    assert mod._dist_tag("0.6.0") == []


@pytest.mark.parametrize("damage", ["missing", "mixed-version", "asset-digest", "extra-asset"])
def test_browser_is_required_and_bound_to_the_same_exact_cohort(
    tmp_path: Path, damage: str
) -> None:
    mod = _release(tmp_path)
    browser = tmp_path / f"artifact-{mod.EXPECTED_NAMES.index(mod.BROWSER)}.tgz"
    if damage == "missing":
        browser.unlink()
    else:
        with tarfile.open(browser) as archive:
            files = {
                member.name.removeprefix("package/"): archive.extractfile(member).read()
                for member in archive.getmembers()
            }
        manifest = json.loads(files.pop("package.json"))
        if damage == "mixed-version":
            manifest["version"] = "1.2.4"
        elif damage == "asset-digest":
            files["dist/index.js"] = b"tampered"
        else:
            files["dist/extra.js"] = b"unexpected"
        _pack(browser, manifest, files)
    with pytest.raises(
        ValueError, match=r"seven|identity/version|manifest mismatch|dist inventory"
    ):
        mod.load_release(tmp_path)


def test_release_tag_version_and_check_mode_fail_before_registry_access(
    tmp_path: Path, monkeypatch
) -> None:
    mod = _release(tmp_path, "0.6.0-rc.1")

    def registry(*args, **kwargs):
        pytest.fail("check mode must not contact the registry")

    monkeypatch.setattr(mod, "_registry_dist", registry)
    assert mod.main([str(tmp_path), "--tag", "xyg-v0.6.0-rc.1", "--check"]) == 0
    assert mod.main([str(tmp_path), "--tag", "xyg-v0.6.0-rc.2", "--check"]) == 1


def test_late_existing_mismatch_prevents_all_new_uploads(tmp_path: Path, monkeypatch) -> None:
    mod = _release(tmp_path)
    artifacts = mod.load_release(tmp_path)

    def registry(spec):
        return (
            mod.RegistryDist("wrong", "sha512-wrong") if spec.startswith(mod.FACADE + "@") else None
        )

    monkeypatch.setattr(mod, "_registry_dist", registry)
    monkeypatch.setattr(
        mod.subprocess,
        "run",
        lambda *args, **kwargs: pytest.fail("must reject the cohort before publishing any package"),
    )
    with pytest.raises(RuntimeError, match="immutable registry mismatch"):
        mod.publish_release(artifacts)


def test_pre_pypi_cli_rejects_missing_browser_without_registry_access(
    tmp_path: Path, monkeypatch
) -> None:
    mod = _release(tmp_path, "0.6.0-rc.1")
    (tmp_path / f"artifact-{mod.EXPECTED_NAMES.index(mod.BROWSER)}.tgz").unlink()
    monkeypatch.setattr(
        mod,
        "_registry_dist",
        lambda spec: pytest.fail("incomplete archives must fail before registry access"),
    )
    assert mod.main([str(tmp_path), "--tag", "xyg-v0.6.0-rc.1", "--check"]) == 1
