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


def _fixtures(tmp_path: Path, *, compatibility: bytes | None = None) -> dict[str, Path]:
    if compatibility is None:
        compatibility = (
            Path(__file__).resolve().parents[1] / "python/xyg/graphforge-compatibility.json"
        ).read_bytes()
    native = b"ELF exact Rust core"
    client = b"export const xyg=true;"
    wheel = tmp_path / "xyg.whl"
    with zipfile.ZipFile(wheel, "w") as archive:
        archive.writestr("xyg-1.2.3rc4.dist-info/METADATA", "Name: xyg\nVersion: 1.2.3rc4\n")
        archive.writestr("xyg/_native_lib/libxyg_core.so", native)
        archive.writestr("xyg/static/standalone.js", client)
        archive.writestr("xyg/graphforge-compatibility.json", compatibility)
    facade = _tgz(
        tmp_path / "facade.tgz",
        {
            "package/package.json": json.dumps(
                {"name": "@curatelabs/xyg-node", "version": "1.2.3-rc.4"}
            ).encode(),
            "package/client/standalone.js": client,
            "package/graphforge-compatibility.json": compatibility,
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
        "package/graphforge-compatibility.json": compatibility,
        **{f"package/dist/{name}": payload for name, payload in assets.items()},
    }
    browser = _tgz(tmp_path / "browser.tgz", browser_files)
    return {"wheel": wheel, "facade": facade, "native": node_native, "browser": browser}


def test_release_cohort_binds_exact_cross_host_bytes(tmp_path: Path) -> None:
    files = _fixtures(tmp_path)
    ledger = cohort.verify(tag="xyg-v1.2.3-rc.4", commit="a" * 40, **files)
    assert ledger["npmVersion"] == "1.2.3-rc.4"
    assert ledger["pythonVersion"] == "1.2.3rc4"
    assert ledger["platform"] == "linux-x64"
    assert len(ledger["artifacts"]) == 4
    assert ledger["supportedCoreVersions"] == _declaration()["supportedCoreVersions"]
    with zipfile.ZipFile(files["wheel"]) as archive:
        assert ledger["graphforgeCompatibilitySha256"] == cohort._digest(
            archive.read("xyg/graphforge-compatibility.json")
        )


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


def test_release_cohort_rejects_malformed_manifest_entry(tmp_path: Path) -> None:
    files = _fixtures(tmp_path)
    archive = cohort._read_tgz(files["browser"])
    manifest = json.loads(archive["package/ASSET-MANIFEST.json"])
    manifest["assets"]["index.js"] = "not an integrity record"
    archive["package/ASSET-MANIFEST.json"] = json.dumps(manifest).encode()
    files["browser"] = _tgz(tmp_path / "browser-malformed.tgz", archive)
    with pytest.raises(ValueError, match="must be an object"):
        cohort.verify(tag="xyg-v1.2.3rc4", commit="a" * 40, **files)


def test_release_cohort_rejects_disagreeing_core_compatibility(tmp_path: Path) -> None:
    files = _fixtures(tmp_path)
    archive = cohort._read_tgz(files["facade"])
    declaration = json.loads(archive["package/graphforge-compatibility.json"])
    declaration["supportedCoreVersions"] = ["0.6.0-rc.5"]
    archive["package/graphforge-compatibility.json"] = json.dumps(declaration).encode()
    files["facade"] = _tgz(tmp_path / "facade-mismatch.tgz", archive)
    with pytest.raises(ValueError, match="different Core compatibility"):
        cohort.verify(tag="xyg-v1.2.3-rc.4", commit="a" * 40, **files)


def test_release_cohort_rejects_identical_incomplete_core_declarations(tmp_path: Path) -> None:
    declaration = {"schemaVersion": 1, "supportedCoreVersions": ["0.5.2"]}
    payload = json.dumps(declaration).encode()
    files = _fixtures(tmp_path, compatibility=payload)
    with zipfile.ZipFile(files["wheel"]) as archive:
        assert archive.read("xyg/graphforge-compatibility.json") == payload
    for role in ("facade", "browser"):
        assert cohort._read_tgz(files[role])["package/graphforge-compatibility.json"] == payload
    with pytest.raises(ValueError, match="Core compatibility"):
        cohort.verify(tag="xyg-v1.2.3-rc.4", commit="a" * 40, **files)


def _declaration() -> dict:
    return json.loads(
        (
            Path(__file__).resolve().parents[1] / "python/xyg/graphforge-compatibility.json"
        ).read_bytes()
    )


@pytest.mark.parametrize("declaration", [None, False, 1, "declaration", []])
def test_release_cohort_rejects_nonobject_core_declarations(tmp_path: Path, declaration) -> None:
    files = _fixtures(tmp_path, compatibility=json.dumps(declaration).encode())
    with pytest.raises(ValueError, match="Core compatibility"):
        cohort.verify(tag="xyg-v1.2.3-rc.4", commit="a" * 40, **files)


@pytest.mark.parametrize(
    "field",
    [
        "schemaVersion",
        "ledgerVersion",
        "algorithmSchemaVersions",
        "searchSchemaVersions",
        "supportedCoreVersions",
        "evidence",
    ],
)
def test_release_cohort_rejects_missing_core_contract_fields(tmp_path: Path, field: str) -> None:
    declaration = _declaration()
    del declaration[field]
    files = _fixtures(tmp_path, compatibility=json.dumps(declaration).encode())
    with pytest.raises(ValueError, match="Core compatibility"):
        cohort.verify(tag="xyg-v1.2.3-rc.4", commit="a" * 40, **files)


@pytest.mark.parametrize(
    "field,value",
    [
        ("schemaVersion", True),
        ("schemaVersion", 1.0),
        ("schemaVersion", 2),
        ("ledgerVersion", True),
        ("ledgerVersion", 0),
        ("ledgerVersion", 1.0),
        ("ledgerVersion", "2"),
        ("algorithmSchemaVersions", []),
        ("algorithmSchemaVersions", [True]),
        ("algorithmSchemaVersions", [1.0]),
        ("algorithmSchemaVersions", [0]),
        ("algorithmSchemaVersions", [1, 1]),
        ("algorithmSchemaVersions", [{}]),
        ("searchSchemaVersions", None),
        ("searchSchemaVersions", []),
        ("searchSchemaVersions", [True]),
        ("searchSchemaVersions", [1.0]),
        ("searchSchemaVersions", [-1]),
        ("searchSchemaVersions", [1, 1]),
        ("supportedCoreVersions", []),
        ("supportedCoreVersions", ["0.5.2", "0.5.2"]),
        ("supportedCoreVersions", [True]),
        ("supportedCoreVersions", ["0.6.0rc5"]),
        ("supportedCoreVersions", ["0.5.*"]),
        ("evidence", []),
        ("evidence", {}),
        ("evidence", [None]),
    ],
)
def test_release_cohort_rejects_malformed_core_contract_fields(
    tmp_path: Path, field: str, value
) -> None:
    declaration = _declaration()
    declaration[field] = value
    files = _fixtures(tmp_path, compatibility=json.dumps(declaration).encode())
    with pytest.raises(ValueError):
        cohort.verify(tag="xyg-v1.2.3-rc.4", commit="a" * 40, **files)


@pytest.mark.parametrize(
    "field", ["coreVersion", "coreSourceCommit", "contractCorpusSha256", "resultManifestSha256"]
)
def test_release_cohort_rejects_incomplete_core_evidence(tmp_path: Path, field: str) -> None:
    declaration = _declaration()
    del declaration["evidence"][0][field]
    files = _fixtures(tmp_path, compatibility=json.dumps(declaration).encode())
    with pytest.raises(ValueError, match="Core compatibility evidence"):
        cohort.verify(tag="xyg-v1.2.3-rc.4", commit="a" * 40, **files)


@pytest.mark.parametrize(
    "field,value",
    [
        ("coreVersion", None),
        ("coreVersion", ["0.5.2"]),
        ("coreVersion", "9.8.7"),
        ("coreSourceCommit", "A" * 40),
        ("coreSourceCommit", "a" * 39),
        ("coreSourceCommit", True),
        ("contractCorpusSha256", "A" * 64),
        ("contractCorpusSha256", "a" * 63),
        ("contractCorpusSha256", None),
        ("resultManifestSha256", "g" * 64),
        ("resultManifestSha256", "a" * 65),
        ("resultManifestSha256", 1),
    ],
)
def test_release_cohort_rejects_malformed_or_mismatched_core_evidence(
    tmp_path: Path, field: str, value
) -> None:
    declaration = _declaration()
    declaration["evidence"][0][field] = value
    files = _fixtures(tmp_path, compatibility=json.dumps(declaration).encode())
    with pytest.raises(ValueError, match="Core compatibility evidence"):
        cohort.verify(tag="xyg-v1.2.3-rc.4", commit="a" * 40, **files)


@pytest.mark.parametrize("duplicate", [False, True])
def test_release_cohort_requires_one_evidence_record_per_supported_core(
    tmp_path: Path, duplicate: bool
) -> None:
    declaration = _declaration()
    if duplicate:
        declaration["evidence"].append(declaration["evidence"][0])
    else:
        declaration["evidence"].pop()
    files = _fixtures(tmp_path, compatibility=json.dumps(declaration).encode())
    with pytest.raises(ValueError, match="Core compatibility evidence"):
        cohort.verify(tag="xyg-v1.2.3-rc.4", commit="a" * 40, **files)


def test_release_cohort_accepts_exact_evidence_without_hardcoded_core_versions(
    tmp_path: Path,
) -> None:
    declaration = _declaration()
    declaration["supportedCoreVersions"] = ["9.8.7-beta.6"]
    declaration["evidence"] = [{**declaration["evidence"][0], "coreVersion": "9.8.7-beta.6"}]
    payload = json.dumps(declaration).encode()
    files = _fixtures(tmp_path, compatibility=payload)
    ledger = cohort.verify(tag="xyg-v1.2.3-rc.4", commit="a" * 40, **files)
    assert ledger["supportedCoreVersions"] == ["9.8.7-beta.6"]
    assert ledger["graphforgeCompatibilitySha256"] == cohort._digest(payload)
