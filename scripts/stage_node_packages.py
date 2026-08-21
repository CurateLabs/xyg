#!/usr/bin/env python3
"""Stage publishable, exact-version XYG Node packages from release artifacts.

The tracked manifests deliberately stay ``private`` and use local ``file:``
optional dependencies so a source checkout cannot publish accidentally.  This
script creates a separate release tree with immutable semver manifests:

* one ``@curatelabs/xyg-node-<platform>`` package from a matching wheel; or
* the ``@curatelabs/xyg-node`` facade with the exact standalone paint client.

No source tree is rewritten in place.  Every staged tree is inventory-checked
before it can be packed by the release workflow.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PACKAGES = ROOT / "packages"

PLATFORMS = {
    "darwin-arm64": ("libxyg_core.dylib", "darwin", "arm64"),
    "darwin-x64": ("libxyg_core.dylib", "darwin", "x64"),
    "linux-arm64": ("libxyg_core.so", "linux", "arm64"),
    "linux-x64": ("libxyg_core.so", "linux", "x64"),
    "win32-x64": ("xyg_core.dll", "win32", "x64"),
}

PRERELEASE_IDENTIFIER = r"(?:0|[1-9][0-9]*|[0-9]*[A-Za-z-][0-9A-Za-z-]*)"
SEMVER_RE = re.compile(
    r"^(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)"
    rf"(?:-{PRERELEASE_IDENTIFIER}(?:\.{PRERELEASE_IDENTIFIER})*)?$"
)
TAG_RE = re.compile(
    r"^xyg-v(?P<base>(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*))"
    r"(?:(?P<pre>a|b|rc)(?P<num>0|[1-9][0-9]*))?$"
)
REPOSITORY = {"type": "git", "url": "git+https://github.com/CurateLabs/xyg.git"}
PUBLISH_CONFIG = {"access": "public", "provenance": True}
NATIVE_BUDGET_BYTES = 40 * 1024 * 1024


def npm_version_from_tag(tag: str) -> str:
    """Map the canonical PEP 440 release tag to its semver npm spelling."""

    match = TAG_RE.fullmatch(tag)
    if match is None:
        raise ValueError(
            f"invalid XYG release tag {tag!r}; expected xyg-vX.Y.Z with optional aN/bN/rcN"
        )
    version = match.group("base")
    if match.group("pre"):
        label = {"a": "alpha", "b": "beta", "rc": "rc"}[match.group("pre")]
        version += f"-{label}.{match.group('num')}"
    return version


def _require_semver(version: str) -> None:
    if SEMVER_RE.fullmatch(version) is None:
        raise ValueError(f"invalid npm semver {version!r}")


def _fresh_dir(path: Path) -> None:
    if path.exists():
        shutil.rmtree(path)
    path.mkdir(parents=True)


def _copy_file(source: Path, destination: Path) -> None:
    if not source.is_file():
        raise FileNotFoundError(source)
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)


def _write_manifest(path: Path, manifest: dict[str, object]) -> None:
    path.write_text(json.dumps(manifest, indent=2, sort_keys=False) + "\n", encoding="utf-8")


def _release_manifest(source: Path, version: str) -> dict[str, object]:
    manifest = json.loads(source.read_text(encoding="utf-8"))
    manifest.pop("private", None)
    manifest["version"] = version
    manifest["repository"] = REPOSITORY
    manifest["publishConfig"] = PUBLISH_CONFIG
    return manifest


def _native_from_wheel(wheel: Path, library_name: str) -> bytes:
    if not wheel.is_file() or wheel.suffix != ".whl":
        raise ValueError(f"native source must be one wheel, got {wheel}")
    with zipfile.ZipFile(wheel) as archive:
        expected = f"xyg/_native_lib/{library_name}"
        matches = [name for name in archive.namelist() if name == expected]
        if len(matches) != 1:
            raise ValueError(
                f"{wheel.name} must contain exactly one xyg/_native_lib/{library_name}; "
                f"found {matches}"
            )
        info = archive.getinfo(matches[0])
        if info.file_size > NATIVE_BUDGET_BYTES:
            raise ValueError(f"{library_name} exceeds {NATIVE_BUDGET_BYTES} byte package budget")
        return archive.read(info)


def _native_arch(payload: bytes) -> tuple[str, str]:
    """Return the executable format and architecture from bounded headers."""

    if payload.startswith(b"\x7fELF") and len(payload) >= 20:
        if payload[4] != 2 or payload[5] not in {1, 2}:
            raise ValueError("native payload has an unsupported or truncated executable header")
        byteorder = "little" if payload[5] == 1 else "big"
        machine = int.from_bytes(payload[18:20], byteorder)
        arch = {62: "x64", 183: "arm64"}.get(machine)
        if arch:
            return "linux", arch
    if payload[:4] in {b"\xcf\xfa\xed\xfe", b"\xfe\xed\xfa\xcf"} and len(payload) >= 8:
        byteorder = "little" if payload[:4] == b"\xcf\xfa\xed\xfe" else "big"
        cpu = int.from_bytes(payload[4:8], byteorder)
        arch = {0x01000007: "x64", 0x0100000C: "arm64"}.get(cpu)
        if arch:
            return "darwin", arch
    if payload.startswith(b"MZ") and len(payload) >= 64:
        offset = int.from_bytes(payload[0x3C:0x40], "little")
        if offset + 6 <= len(payload) and payload[offset : offset + 4] == b"PE\0\0":
            machine = int.from_bytes(payload[offset + 4 : offset + 6], "little")
            if machine == 0x8664:
                return "win32", "x64"
    raise ValueError("native payload has an unsupported or truncated executable header")


def validate_native_payload(payload: bytes, platform_id: str) -> None:
    """Validate one platform package's bounded native executable bytes."""

    if platform_id not in PLATFORMS:
        raise ValueError(f"unsupported Node platform {platform_id!r}")
    library_name, expected_os, expected_cpu = PLATFORMS[platform_id]
    if not payload:
        raise ValueError(f"{platform_id} native {library_name} is empty")
    if len(payload) > NATIVE_BUDGET_BYTES:
        raise ValueError(f"{platform_id} native exceeds {NATIVE_BUDGET_BYTES} byte package budget")
    actual_os, actual_cpu = _native_arch(payload)
    if (actual_os, actual_cpu) != (expected_os, expected_cpu):
        raise ValueError(f"{platform_id} package contains {actual_os}-{actual_cpu} native bytes")


def stage_platform(*, platform_id: str, wheel: Path, output: Path, version: str) -> Path:
    _require_semver(version)
    if platform_id not in PLATFORMS:
        raise ValueError(f"unsupported Node platform {platform_id!r}")
    library_name, expected_os, expected_cpu = PLATFORMS[platform_id]
    source = PACKAGES / f"xyg-node-{platform_id}"
    destination = output / f"xyg-node-{platform_id}"
    _fresh_dir(destination)
    for name in ("index.js", "README.md", "NOTICE"):
        _copy_file(source / name, destination / name)
    _copy_file(ROOT / "LICENSE", destination / "LICENSE")
    native_payload = _native_from_wheel(wheel, library_name)
    validate_native_payload(native_payload, platform_id)
    (destination / library_name).write_bytes(native_payload)

    manifest = _release_manifest(source / "package.json", version)
    manifest["files"] = ["index.js", library_name, "README.md", "NOTICE", "LICENSE"]
    _write_manifest(destination / "package.json", manifest)
    _verify_platform(destination, platform_id, version, expected_os, expected_cpu, library_name)
    return destination


def stage_facade(*, client: Path, output: Path, version: str) -> Path:
    _require_semver(version)
    source = PACKAGES / "xy-node"
    destination = output / "xyg-node"
    _fresh_dir(destination)
    shutil.copytree(source / "src", destination / "src")
    for name in ("README.md", "NOTICE"):
        _copy_file(source / name, destination / name)
    _copy_file(ROOT / "LICENSE", destination / "LICENSE")
    _copy_file(client, destination / "client" / "standalone.js")

    manifest = _release_manifest(source / "package.json", version)
    manifest["optionalDependencies"] = {
        f"@curatelabs/xyg-node-{platform_id}": version for platform_id in sorted(PLATFORMS)
    }
    manifest["files"] = ["src", "client/standalone.js", "README.md", "NOTICE", "LICENSE"]
    _write_manifest(destination / "package.json", manifest)
    _verify_facade(destination, version, client)
    return destination


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _verify_common(directory: Path, expected_name: str, version: str) -> dict[str, object]:
    manifest = json.loads((directory / "package.json").read_text(encoding="utf-8"))
    if manifest.get("name") != expected_name:
        raise ValueError(f"staged name mismatch: {manifest.get('name')!r} != {expected_name!r}")
    if manifest.get("version") != version:
        raise ValueError(f"staged version mismatch: {manifest.get('version')!r} != {version!r}")
    if manifest.get("private") is not None:
        raise ValueError(f"{expected_name} staged manifest must not contain private")
    if manifest.get("repository") != REPOSITORY:
        raise ValueError(f"{expected_name} repository identity mismatch")
    if manifest.get("publishConfig") != PUBLISH_CONFIG:
        raise ValueError(f"{expected_name} publishConfig mismatch")
    return manifest


def _verify_platform(
    directory: Path,
    platform_id: str,
    version: str,
    expected_os: str,
    expected_cpu: str,
    library_name: str,
) -> None:
    manifest = _verify_common(directory, f"@curatelabs/xyg-node-{platform_id}", version)
    if manifest.get("os") != [expected_os] or manifest.get("cpu") != [expected_cpu]:
        raise ValueError(f"{platform_id} staged os/cpu mismatch")
    native = directory / library_name
    if not native.is_file() or native.stat().st_size == 0:
        raise ValueError(f"{platform_id} staged native is missing or empty")


def _verify_facade(directory: Path, version: str, source_client: Path) -> None:
    manifest = _verify_common(directory, "@curatelabs/xyg-node", version)
    main = manifest.get("main")
    exports = manifest.get("exports")
    exported_main = exports.get(".") if isinstance(exports, dict) else None
    if not isinstance(main, str) or exported_main != main:
        raise ValueError("facade main and root export must identify the same entry point")
    entry = directory / main.removeprefix("./")
    if not entry.is_file() or directory.resolve() not in entry.resolve().parents:
        raise ValueError("facade entry point is missing from the staged tree")
    expected = {f"@curatelabs/xyg-node-{platform_id}": version for platform_id in sorted(PLATFORMS)}
    if manifest.get("optionalDependencies") != expected:
        raise ValueError("facade optionalDependencies are not exact-version aligned")
    staged_client = directory / "client" / "standalone.js"
    if _sha256(staged_client) != _sha256(source_client):
        raise ValueError("facade standalone client drifted during staging")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    version_group = parser.add_mutually_exclusive_group(required=True)
    version_group.add_argument("--tag", help="canonical xyg-v* release tag")
    version_group.add_argument("--version", help="explicit npm semver (dry-run/testing)")
    parser.add_argument("--output", type=Path, required=True)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--facade", action="store_true")
    mode.add_argument("--platform", choices=sorted(PLATFORMS))
    parser.add_argument("--wheel", type=Path)
    parser.add_argument("--client", type=Path)
    args = parser.parse_args(argv)

    try:
        version = npm_version_from_tag(args.tag) if args.tag else args.version
        assert version is not None
        if args.facade:
            if args.client is None:
                parser.error("--facade requires --client")
            staged = stage_facade(client=args.client, output=args.output, version=version)
        else:
            if args.wheel is None:
                parser.error("--platform requires --wheel")
            staged = stage_platform(
                platform_id=args.platform,
                wheel=args.wheel,
                output=args.output,
                version=version,
            )
    except (FileNotFoundError, ValueError, zipfile.BadZipFile) as error:
        print(f"node package staging failed: {error}", file=sys.stderr)
        return 1
    print(f"staged {staged.name}@{version} at {staged}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
