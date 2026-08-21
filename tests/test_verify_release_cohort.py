"""Cross-host immutable release cohort verification."""

from __future__ import annotations

import io
import json
import tarfile
import zipfile
from pathlib import Path

import pytest
from scripts import verify_release_cohort as cohort


def _tgz(path: Path, files: dict[str, bytes]) -> Path:
    with tarfile.open(path, "w:gz") as archive:
        for name, payload in files.items():
            member = tarfile.TarInfo(name)
            member.size = len(payload)
            archive.addfile(member, io.BytesIO(payload))
    return path


def _fixtures(tmp_path: Path) -> dict[str, Path]:
    native = b"ELF exact Rust core"
    client = b"export const xyg=true;"
    wheel = tmp_path / "xyg.whl"
    with zipfile.ZipFile(wheel, "w") as archive:
        archive.writestr("xyg-1.2.3rc4.dist-info/METADATA", "Name: xyg\nVersion: 1.2.3rc4\n")
        archive.writestr("xyg/_native_lib/libxyg_core.so", native)
        archive.writestr("xyg/static/standalone.js", client)
    facade = _tgz(
        tmp_path / "facade.tgz",
        {
            "package/package.json": json.dumps(
                {"name": "@curatelabs/xyg-node", "version": "1.2.3-rc.4"}
            ).encode(),
            "package/client/standalone.js": client,
        },
    )
    node_native = _tgz(
        tmp_path / "native.tgz",
        {
            "package/package.json": json.dumps(
                {"name": "@curatelabs/xyg-node-linux-x64", "version": "1.2.3-rc.4"}
            ).encode(),
            "package/libxyg_core.so": native,
        },
    )
    assets = {
        "standalone.js": client,
        "index.js": b"export {};",
        "wasm-worker.js": b"export {};",
        "xyg-wasm.wasm": b"\0asm\x01\0\0\0",
    }
    manifest = {
        "packageVersion": "1.2.3-rc.4",
        "assets": {
            name: {"bytes": len(payload), "sha256": cohort._digest(payload)}
            for name, payload in assets.items()
        },
    }
    browser_files = {
        "package/package.json": json.dumps(
            {"name": "@curatelabs/xyg", "version": "1.2.3-rc.4"}
        ).encode(),
        "package/ASSET-MANIFEST.json": json.dumps(manifest).encode(),
        **{f"package/dist/{name}": payload for name, payload in assets.items()},
    }
    browser = _tgz(tmp_path / "browser.tgz", browser_files)
    return {"wheel": wheel, "facade": facade, "native": node_native, "browser": browser}


def test_release_cohort_binds_exact_cross_host_bytes(tmp_path: Path) -> None:
    files = _fixtures(tmp_path)
    ledger = cohort.verify(tag="xyg-v1.2.3rc4", commit="a" * 40, **files)
    assert ledger["npmVersion"] == "1.2.3-rc.4"
    assert ledger["pythonVersion"] == "1.2.3rc4"
    assert ledger["platform"] == "linux-x64"
    assert len(ledger["artifacts"]) == 4


def test_release_cohort_rejects_cross_host_client_drift(tmp_path: Path) -> None:
    files = _fixtures(tmp_path)
    files["facade"] = _tgz(
        tmp_path / "facade-drift.tgz",
        {
            "package/package.json": json.dumps(
                {"name": "@curatelabs/xyg-node", "version": "1.2.3-rc.4"}
            ).encode(),
            "package/client/standalone.js": b"drift",
        },
    )
    with pytest.raises(ValueError, match=r"different standalone\.js"):
        cohort.verify(tag="xyg-v1.2.3rc4", commit="a" * 40, **files)


def test_release_cohort_rejects_manifest_drift(tmp_path: Path) -> None:
    files = _fixtures(tmp_path)
    archive = cohort._read_tgz(files["browser"])
    manifest = json.loads(archive["package/ASSET-MANIFEST.json"])
    manifest["assets"]["index.js"]["sha256"] = "0" * 64
    archive["package/ASSET-MANIFEST.json"] = json.dumps(manifest).encode()
    files["browser"] = _tgz(tmp_path / "browser-drift.tgz", archive)
    with pytest.raises(ValueError, match="manifest mismatch"):
        cohort.verify(tag="xyg-v1.2.3rc4", commit="a" * 40, **files)
