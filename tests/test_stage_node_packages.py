"""Release staging contracts for the XYG Node package set (#52)."""

from __future__ import annotations

import importlib.util
import json
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "scripts" / "stage_node_packages.py"


def _load():
    spec = importlib.util.spec_from_file_location("stage_node_packages", SCRIPT)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def _elf(arch: str) -> bytes:
    payload = bytearray(64)
    payload[:6] = b"\x7fELF\x02\x01"
    payload[18:20] = {"x64": 62, "arm64": 183}[arch].to_bytes(2, "little")
    return bytes(payload)


def _macho(arch: str) -> bytes:
    return b"\xcf\xfa\xed\xfe" + {
        "x64": 0x01000007,
        "arm64": 0x0100000C,
    }[arch].to_bytes(4, "little")


def _pe_x64() -> bytes:
    payload = bytearray(80)
    payload[:2] = b"MZ"
    payload[0x3C:0x40] = (64).to_bytes(4, "little")
    payload[64:68] = b"PE\0\0"
    payload[68:70] = (0x8664).to_bytes(2, "little")
    return bytes(payload)


def _wheel(path: Path, library: str, payload: bytes | None = None) -> Path:
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr(f"xyg/_native_lib/{library}", payload or _elf("x64"))
    return path


@pytest.mark.parametrize(
    ("tag", "expected"),
    [
        ("xyg-v0.6.0", "0.6.0"),
        ("xyg-v0.6.0a1", "0.6.0-alpha.1"),
        ("xyg-v0.6.0b2", "0.6.0-beta.2"),
        ("xyg-v0.6.0rc3", "0.6.0-rc.3"),
    ],
)
def test_release_tag_maps_to_npm_semver(tag: str, expected: str) -> None:
    assert _load().npm_version_from_tag(tag) == expected


@pytest.mark.parametrize(
    ("suffix", "npm_label"), [("a01", "alpha"), ("b01", "beta"), ("rc01", "rc")]
)
def test_release_version_rejects_leading_zero_prerelease_counter(
    suffix: str, npm_label: str
) -> None:
    mod = _load()
    with pytest.raises(ValueError, match="invalid XYG release tag"):
        mod.npm_version_from_tag(f"xyg-v0.6.0{suffix}")
    with pytest.raises(ValueError, match="invalid npm semver"):
        mod._require_semver(f"0.6.0-{npm_label}.01")


@pytest.mark.parametrize("tag", ["xyg-v01.2.3", "xyg-v1.02.3", "xyg-v1.2.03"])
def test_release_version_rejects_leading_zero_release_segment(tag: str) -> None:
    with pytest.raises(ValueError, match="invalid XYG release tag"):
        _load().npm_version_from_tag(tag)


@pytest.mark.parametrize(
    ("payload", "expected"),
    [
        (_elf("x64"), ("linux", "x64")),
        (_elf("arm64"), ("linux", "arm64")),
        (_macho("x64"), ("darwin", "x64")),
        (_macho("arm64"), ("darwin", "arm64")),
        (_pe_x64(), ("win32", "x64")),
    ],
)
def test_native_header_architecture_probe(payload: bytes, expected: tuple[str, str]) -> None:
    assert _load()._native_arch(payload) == expected


def test_platform_staging_embeds_exact_wheel_native(tmp_path: Path) -> None:
    mod = _load()
    payload = _elf("x64")
    wheel = _wheel(tmp_path / "xyg.whl", "libxyg_core.so", payload)
    staged = mod.stage_platform(
        platform_id="linux-x64", wheel=wheel, output=tmp_path / "out", version="0.6.0"
    )
    manifest = json.loads((staged / "package.json").read_text(encoding="utf-8"))
    assert manifest["name"] == "@curatelabs/xyg-node-linux-x64"
    assert manifest["version"] == "0.6.0"
    assert "private" not in manifest
    assert manifest["publishConfig"] == {"access": "public", "provenance": True}
    assert (staged / "libxyg_core.so").read_bytes() == payload
    assert (staged / "LICENSE").is_file()


def test_facade_staging_locks_optionals_and_embeds_client(tmp_path: Path) -> None:
    mod = _load()
    client = tmp_path / "standalone.js"
    client.write_text("var xyg={renderStandalone(){}};", encoding="utf-8")
    staged = mod.stage_facade(client=client, output=tmp_path / "out", version="0.6.0-rc.1")
    manifest = json.loads((staged / "package.json").read_text(encoding="utf-8"))
    assert manifest["version"] == "0.6.0-rc.1"
    assert set(manifest["optionalDependencies"]) == {
        f"@curatelabs/xyg-node-{platform}" for platform in mod.PLATFORMS
    }
    assert set(manifest["optionalDependencies"].values()) == {"0.6.0-rc.1"}
    assert (staged / "client" / "standalone.js").read_bytes() == client.read_bytes()
    assert "client/standalone.js" in manifest["files"]
    (staged / "src" / "index.js").unlink()
    with pytest.raises(ValueError, match="entry point is missing"):
        mod._verify_facade(staged, "0.6.0-rc.1", client)
    (staged / "src" / "index.js").write_text("export {};", encoding="utf-8")

    if shutil.which("node") is None:
        pytest.skip("node is required for the offline facade probe")
    probe = subprocess.run(
        [
            "node",
            "--input-type=module",
            "--eval",
            """
const { toHtml } = await import(`file://${process.argv[1]}`);
const html = toHtml({spec:{protocol:12,width:10,height:10},buffers:new Uint8Array()});
if (!html.includes("<title>XYG</title>")) throw new Error("stale default title");
if (!html.includes("renderStandalone")) throw new Error("offline client missing");
""",
            str(staged / "src" / "html.js"),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert probe.returncode == 0, probe.stderr


def test_staging_rejects_wrong_or_ambiguous_native(tmp_path: Path) -> None:
    mod = _load()
    wheel = tmp_path / "xyg.whl"
    with zipfile.ZipFile(wheel, "w") as archive:
        archive.writestr("xyg/_native_lib/libxyg_core.dylib", b"wrong")
    with pytest.raises(ValueError, match="exactly one"):
        mod.stage_platform(
            platform_id="linux-x64", wheel=wheel, output=tmp_path / "out", version="0.6.0"
        )

    wrong_arch = _wheel(tmp_path / "wrong.whl", "libxyg_core.so", payload=_elf("arm64"))
    with pytest.raises(ValueError, match="contains linux-arm64"):
        mod.stage_platform(
            platform_id="linux-x64",
            wheel=wrong_arch,
            output=tmp_path / "out",
            version="0.6.0",
        )

    prefixed = tmp_path / "prefixed.whl"
    with zipfile.ZipFile(prefixed, "w") as archive:
        archive.writestr("unexpected/xyg/_native_lib/libxyg_core.so", _elf("x64"))
    with pytest.raises(ValueError, match="exactly one"):
        mod.stage_platform(
            platform_id="linux-x64",
            wheel=prefixed,
            output=tmp_path / "out",
            version="0.6.0",
        )


def test_source_manifests_remain_publish_safe() -> None:
    for manifest_path in [
        REPO / "packages" / "xy-node" / "package.json",
        *(REPO / "packages").glob("xyg-node-*/package.json"),
    ]:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        assert manifest["private"] is True
        assert manifest["version"] == "0.0.0"
