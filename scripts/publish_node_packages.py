#!/usr/bin/env python3
"""Publish the complete XYG Node package set with safe immutable retries.

npm versions are immutable, while a release contains five native packages and
one facade. A network failure can therefore leave a prefix published. On a
retry, this command skips an existing artifact only when the registry's SHA-1
is byte-identical to the local tarball; any mismatch fails closed. Native
packages are always processed before the facade.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import tarfile
from dataclasses import dataclass
from pathlib import Path

try:
    from stage_node_packages import (
        NATIVE_BUDGET_BYTES,
        validate_native_payload,
    )
    from stage_node_packages import (
        PLATFORMS as PLATFORM_LAYOUTS,
    )
except ModuleNotFoundError:  # Imported as ``scripts.publish_node_packages`` in tests.
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
EXPECTED_NAMES = tuple(f"{FACADE}-{platform}" for platform in PLATFORMS) + (FACADE,)
NPM_TIMEOUT_S = 300


@dataclass(frozen=True)
class Artifact:
    path: Path
    name: str
    version: str
    shasum: str
    manifest: dict[str, object]


def _artifact(path: Path) -> Artifact:
    if not path.is_file() or path.suffix != ".tgz":
        raise ValueError(f"expected an npm .tgz artifact, got {path}")
    try:
        with tarfile.open(path, "r:gz") as archive:
            member = archive.getmember("package/package.json")
            handle = archive.extractfile(member)
            if handle is None or member.size > 1024 * 1024:
                raise ValueError(f"{path.name} has an invalid package manifest")
            manifest = json.loads(handle.read().decode("utf-8"))
            if not isinstance(manifest, dict):
                raise ValueError(f"{path.name} package manifest is not a JSON object")
            name = manifest.get("name")
            if isinstance(name, str) and name.startswith(f"{FACADE}-"):
                _validate_native_archive(archive, manifest, name.removeprefix(f"{FACADE}-"))
    except (KeyError, tarfile.TarError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError(f"cannot read {path.name}: {error}") from error
    name = manifest.get("name")
    version = manifest.get("version")
    if not isinstance(name, str) or not isinstance(version, str):
        raise ValueError(f"{path.name} is missing a string name/version")
    return Artifact(path, name, version, hashlib.sha1(path.read_bytes()).hexdigest(), manifest)


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


def load_release(directory: Path) -> list[Artifact]:
    artifacts = [_artifact(path) for path in sorted(directory.rglob("*.tgz"))]
    by_name = {artifact.name: artifact for artifact in artifacts}
    if len(artifacts) != len(EXPECTED_NAMES) or set(by_name) != set(EXPECTED_NAMES):
        raise ValueError(
            "expected exactly the six XYG Node packages; "
            f"found {[artifact.name for artifact in artifacts]}"
        )
    versions = {artifact.version for artifact in artifacts}
    if len(versions) != 1:
        raise ValueError(f"XYG Node package versions are not aligned: {sorted(versions)}")
    version = versions.pop()
    expected_optionals = {name: version for name in EXPECTED_NAMES if name != FACADE}
    if by_name[FACADE].manifest.get("optionalDependencies") != expected_optionals:
        raise ValueError("facade optionalDependencies do not exactly match the staged package set")
    return [by_name[name] for name in EXPECTED_NAMES]


def _registry_shasum(spec: str) -> str | None:
    result = subprocess.run(
        ["npm", "view", spec, "dist.shasum", "--json"],
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
    if not isinstance(value, str) or not value:
        raise RuntimeError(f"npm returned no dist.shasum for existing {spec}")
    return value


def publish_release(artifacts: list[Artifact]) -> None:
    for artifact in artifacts:
        spec = f"{artifact.name}@{artifact.version}"
        remote = _registry_shasum(spec)
        if remote is not None:
            if remote != artifact.shasum:
                raise RuntimeError(
                    f"refusing to skip {spec}: registry SHA-1 {remote} differs from "
                    f"local {artifact.shasum}"
                )
            print(f"already published with identical bytes: {spec}")
            continue
        subprocess.run(
            ["npm", "publish", str(artifact.path), "--access", "public", "--provenance"],
            check=True,
            timeout=NPM_TIMEOUT_S,
        )
        print(f"published {spec}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path, help="directory containing all six .tgz files")
    args = parser.parse_args(argv)
    try:
        publish_release(load_release(args.directory))
    except (
        OSError,
        ValueError,
        RuntimeError,
        subprocess.CalledProcessError,
        subprocess.TimeoutExpired,
    ) as error:
        print(f"XYG Node publication failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
