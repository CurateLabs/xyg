#!/usr/bin/env python3
"""Publish the complete XYG npm package set with safe immutable retries.

npm versions are immutable, while a release contains five native packages and
one browser package and one facade. A network failure can leave a prefix published. On a
retry, this command skips an existing artifact only when the registry's SHA-1
and SHA-512 integrity values are byte-identical to the local tarball; any
mismatch fails closed. New uploads receive the same registry-side confirmation
before the sequence advances. Native packages are always processed before the
facade.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import subprocess
import sys
import tarfile
import time
from dataclasses import dataclass
from pathlib import Path

try:
    from release_version import parse_tag
    from stage_browser_package import ASSETS, EXPECTED_EXPORTS, JS_BUDGET_BYTES, WASM_BUDGET_BYTES
    from stage_node_packages import (
        NATIVE_BUDGET_BYTES,
        validate_native_payload,
    )
    from stage_node_packages import (
        PLATFORMS as PLATFORM_LAYOUTS,
    )
except ModuleNotFoundError:  # Imported as ``scripts.publish_node_packages`` in tests.
    from scripts.release_version import parse_tag
    from scripts.stage_browser_package import (
        ASSETS,
        EXPECTED_EXPORTS,
        JS_BUDGET_BYTES,
        WASM_BUDGET_BYTES,
    )
    from scripts.stage_node_packages import (
        NATIVE_BUDGET_BYTES,
        validate_native_payload,
    )
    from scripts.stage_node_packages import (
        PLATFORMS as PLATFORM_LAYOUTS,
    )

PLATFORMS = (
    "darwin-arm64",
    "darwin-x64",
    "linux-arm64",
    "linux-x64",
    "win32-x64",
)
FACADE = "@curatelabs/xyg-node"
BROWSER = "@curatelabs/xyg"
NATIVE_NAMES = tuple(f"{FACADE}-{platform}" for platform in PLATFORMS)
EXPECTED_NAMES = (*NATIVE_NAMES, BROWSER, FACADE)
NPM_TIMEOUT_S = 300
REGISTRY_VERIFY_ATTEMPTS = 6
REGISTRY_VERIFY_DELAY_S = 2


@dataclass(frozen=True)
class Artifact:
    path: Path
    name: str
    version: str
    shasum: str
    integrity: str
    manifest: dict[str, object]


def _artifact(path: Path) -> Artifact:
    if not path.is_file() or path.suffix != ".tgz":
        raise ValueError(f"expected an npm .tgz artifact, got {path}")
    try:
        with tarfile.open(path, "r:gz") as archive:
            members = archive.getmembers()
            if (
                len({item.name for item in members}) != len(members)
                or any(item.issym() or item.islnk() for item in members)
                or any(
                    item.name.startswith("/") or ".." in Path(item.name).parts for item in members
                )
            ):
                raise ValueError(f"{path.name} contains unsafe, linked, or duplicate paths")
            member = archive.getmember("package/package.json")
            handle = archive.extractfile(member)
            if handle is None or member.size > 1024 * 1024:
                raise ValueError(f"{path.name} has an invalid package manifest")
            manifest = json.loads(handle.read().decode("utf-8"))
            if not isinstance(manifest, dict):
                raise ValueError(f"{path.name} package manifest is not a JSON object")
            name = manifest.get("name")
            if name == BROWSER:
                _validate_browser_archive(archive, manifest)
            if isinstance(name, str) and name.startswith(f"{FACADE}-"):
                _validate_native_archive(archive, manifest, name.removeprefix(f"{FACADE}-"))
    except (KeyError, tarfile.TarError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError(f"cannot read {path.name}: {error}") from error
    name = manifest.get("name")
    version = manifest.get("version")
    if not isinstance(name, str) or not isinstance(version, str):
        raise ValueError(f"{path.name} is missing a string name/version")
    payload = path.read_bytes()
    return Artifact(
        path,
        name,
        version,
        hashlib.sha1(payload).hexdigest(),
        "sha512-" + base64.b64encode(hashlib.sha512(payload).digest()).decode("ascii"),
        manifest,
    )


def _validate_native_archive(
    archive: tarfile.TarFile, manifest: dict[str, object], platform_id: str
) -> None:
    if platform_id not in PLATFORM_LAYOUTS:
        raise ValueError(f"unexpected XYG Node native platform {platform_id!r}")
    library_name, expected_os, expected_cpu = PLATFORM_LAYOUTS[platform_id]
    if manifest.get("os") != [expected_os] or manifest.get("cpu") != [expected_cpu]:
        raise ValueError(f"{platform_id} archive has mismatched os/cpu metadata")
    expected_member = f"package/{library_name}"
    members = [member for member in archive.getmembers() if member.name == expected_member]
    if len(members) != 1 or not members[0].isfile():
        raise ValueError(f"{platform_id} archive must contain exactly one {expected_member}")
    member = members[0]
    if member.size <= 0 or member.size > NATIVE_BUDGET_BYTES:
        raise ValueError(f"{platform_id} archive native size is outside the package budget")
    handle = archive.extractfile(member)
    if handle is None:
        raise ValueError(f"{platform_id} archive native cannot be read")
    validate_native_payload(handle.read(), platform_id)


def _validate_browser_archive(archive: tarfile.TarFile, manifest: dict[str, object]) -> None:
    if manifest.get("exports") != EXPECTED_EXPORTS or manifest.get("type") != "module":
        raise ValueError("browser archive must expose the canonical ESM/IIFE/Worker/WASM paths")
    for key in ("dependencies", "optionalDependencies", "peerDependencies", "scripts", "bin"):
        if manifest.get(key):
            raise ValueError(f"browser archive must not declare {key}")
    member = archive.getmember("package/ASSET-MANIFEST.json")
    stream = archive.extractfile(member)
    if stream is None or member.size > 1024 * 1024:
        raise ValueError("browser archive has an invalid asset manifest")
    inventory = json.loads(stream.read().decode("utf-8"))
    if (
        not isinstance(inventory, dict)
        or inventory.get("schemaVersion") != 1
        or inventory.get("package") != BROWSER
        or inventory.get("packageVersion") != manifest.get("version")
    ):
        raise ValueError("browser asset manifest identity/version does not match package")
    assets = inventory.get("assets")
    if not isinstance(assets, dict) or set(assets) != set(ASSETS):
        raise ValueError("browser asset manifest must list the exact four XYG assets")
    paths = {f"package/dist/{name}" for name in ASSETS}
    if {
        item.name
        for item in archive.getmembers()
        if item.isfile() and item.name.startswith("package/dist/")
    } != paths:
        raise ValueError("browser archive dist inventory must contain the exact four XYG assets")
    for name in ASSETS:
        member = archive.getmember(f"package/dist/{name}")
        stream = archive.extractfile(member)
        budget = WASM_BUDGET_BYTES if name.endswith(".wasm") else JS_BUDGET_BYTES
        if stream is None or not member.isfile() or not 0 < member.size <= budget:
            raise ValueError(f"browser asset {name} is missing or outside the package budget")
        payload = stream.read()
        expected = assets[name]
        if (
            not isinstance(expected, dict)
            or expected.get("bytes") != len(payload)
            or expected.get("sha256") != hashlib.sha256(payload).hexdigest()
        ):
            raise ValueError(f"browser asset manifest mismatch for {name}")
        if name.endswith(".wasm") and not payload.startswith(b"\0asm\x01\0\0\0"):
            raise ValueError("browser WASM asset has an invalid module header")


def load_release(directory: Path, *, tag: str | None = None) -> list[Artifact]:
    artifacts = [_artifact(path) for path in sorted(directory.rglob("*.tgz"))]
    by_name = {artifact.name: artifact for artifact in artifacts}
    if len(artifacts) != len(EXPECTED_NAMES) or set(by_name) != set(EXPECTED_NAMES):
        raise ValueError(
            "expected exactly the seven XYG npm packages; "
            f"found {[artifact.name for artifact in artifacts]}"
        )
    versions = {artifact.version for artifact in artifacts}
    if len(versions) != 1:
        raise ValueError(f"XYG Node package versions are not aligned: {sorted(versions)}")
    version = versions.pop()
    if tag is not None and parse_tag(tag).npm != version:
        raise ValueError(f"npm package version {version!r} does not match release tag {tag!r}")
    expected_optionals = {name: version for name in NATIVE_NAMES}
    if by_name[FACADE].manifest.get("optionalDependencies") != expected_optionals:
        raise ValueError("facade optionalDependencies do not exactly match the staged package set")
    return [by_name[name] for name in EXPECTED_NAMES]


@dataclass(frozen=True)
class RegistryDist:
    shasum: str
    integrity: str


def _registry_dist(spec: str) -> RegistryDist | None:
    result = subprocess.run(
        ["npm", "view", spec, "dist", "--json"],
        check=False,
        capture_output=True,
        text=True,
        timeout=NPM_TIMEOUT_S,
    )
    if result.returncode != 0:
        combined = f"{result.stdout}\n{result.stderr}"
        if "E404" in combined or "is not in this registry" in combined:
            return None
        raise RuntimeError(f"npm view failed for {spec}: {combined.strip()}")
    value = json.loads(result.stdout)
    if not isinstance(value, dict):
        raise RuntimeError(f"npm returned invalid dist metadata for existing {spec}")
    shasum = value.get("shasum")
    integrity = value.get("integrity")
    if not isinstance(shasum, str) or not shasum:
        raise RuntimeError(f"npm returned no dist.shasum for existing {spec}")
    if not isinstance(integrity, str) or not integrity.startswith("sha512-"):
        raise RuntimeError(f"npm returned no SHA-512 dist.integrity for existing {spec}")
    return RegistryDist(shasum, integrity)


def _assert_registry_bytes(artifact: Artifact, remote: RegistryDist) -> None:
    spec = f"{artifact.name}@{artifact.version}"
    mismatches = []
    if remote.shasum != artifact.shasum:
        mismatches.append(f"SHA-1 {remote.shasum} != {artifact.shasum}")
    if remote.integrity != artifact.integrity:
        mismatches.append(f"SHA-512 {remote.integrity} != {artifact.integrity}")
    if mismatches:
        raise RuntimeError(
            f"refusing immutable registry mismatch for {spec}: " + "; ".join(mismatches)
        )


def _confirm_registry_bytes(artifact: Artifact) -> None:
    """Wait briefly for npm visibility, then prove the uploaded tarball bytes."""

    spec = f"{artifact.name}@{artifact.version}"
    for attempt in range(REGISTRY_VERIFY_ATTEMPTS):
        remote = _registry_dist(spec)
        if remote is not None:
            _assert_registry_bytes(artifact, remote)
            print(f"registry integrity confirmed: {spec} ({artifact.integrity})")
            return
        if attempt + 1 < REGISTRY_VERIFY_ATTEMPTS:
            time.sleep(REGISTRY_VERIFY_DELAY_S)
    raise RuntimeError(
        f"npm did not expose {spec} after publication; retry the release to verify immutable bytes"
    )


def _dist_tag(version: str) -> list[str]:
    """npm refuses to publish a prerelease without an explicit dist-tag, and a
    prerelease must never become ``latest``."""
    return ["--tag", "next"] if "-" in version else []


def publish_release(artifacts: list[Artifact]) -> None:
    # Reject a stale retry before uploading any further member of the cohort.
    existing = {}
    for artifact in artifacts:
        remote = _registry_dist(f"{artifact.name}@{artifact.version}")
        if remote is not None:
            _assert_registry_bytes(artifact, remote)
        existing[artifact.name] = remote
    for artifact in artifacts:
        spec = f"{artifact.name}@{artifact.version}"
        if existing[artifact.name] is not None:
            print(f"already published with identical SHA-512 bytes: {spec}")
            continue
        subprocess.run(
            [
                "npm",
                "publish",
                str(artifact.path.resolve()),
                "--access",
                "public",
                "--provenance",
                *_dist_tag(artifact.version),
            ],
            check=True,
            timeout=NPM_TIMEOUT_S,
        )
        print(f"published {spec}")
        _confirm_registry_bytes(artifact)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path, help="directory containing all seven .tgz files")
    parser.add_argument("--tag", help="require every package version to match this XYG release tag")
    parser.add_argument(
        "--check", action="store_true", help="validate archives without registry access"
    )
    args = parser.parse_args(argv)
    try:
        artifacts = load_release(args.directory, tag=args.tag)
        if args.check:
            print("Verified complete seven-package XYG npm cohort")
        else:
            publish_release(artifacts)
    except (
        OSError,
        ValueError,
        RuntimeError,
        subprocess.CalledProcessError,
        subprocess.TimeoutExpired,
    ) as error:
        print(f"XYG npm publication failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
