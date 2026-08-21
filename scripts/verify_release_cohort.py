#!/usr/bin/env python3
"""Verify one exact Linux x64 XYG release cohort and emit its hash ledger."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import tarfile
import zipfile
from pathlib import Path
from typing import Any

try:
    from stage_node_packages import npm_version_from_tag
except ModuleNotFoundError:
    from scripts.stage_node_packages import npm_version_from_tag

EXPECTED = {
    "facade": "@curatelabs/xyg-node",
    "native": "@curatelabs/xyg-node-linux-x64",
    "browser": "@curatelabs/xyg",
}
EXPECTED_BROWSER_ASSETS = {"index.js", "standalone.js", "wasm-worker.js", "xyg-wasm.wasm"}


def _digest(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _read_tgz(path: Path) -> dict[str, bytes]:
    with tarfile.open(path, "r:gz") as archive:
        members = archive.getmembers()
        if any(member.issym() or member.islnk() for member in members):
            raise ValueError(f"{path.name}: release archive must not contain links")
        if any(
            member.name.startswith("/") or ".." in Path(member.name).parts for member in members
        ):
            raise ValueError(f"{path.name}: release archive contains an unsafe path")
        if len({member.name for member in members}) != len(members):
            raise ValueError(f"{path.name}: release archive contains duplicate paths")
        result = {}
        for member in members:
            if not member.isfile():
                continue
            stream = archive.extractfile(member)
            if stream is None:
                raise ValueError(f"{path.name}: cannot read {member.name}")
            result[member.name] = stream.read()
        return result


def _wheel(path: Path) -> tuple[str, str, dict[str, bytes]]:
    with zipfile.ZipFile(path) as archive:
        names = archive.namelist()
        if len(set(names)) != len(names) or any(name.startswith(("/", "../")) for name in names):
            raise ValueError(f"{path.name}: unsafe or duplicate wheel paths")
        files = {name: archive.read(name) for name in names if not name.endswith("/")}
    metadata = [payload for name, payload in files.items() if name.endswith(".dist-info/METADATA")]
    if len(metadata) != 1:
        raise ValueError(f"{path.name}: expected one METADATA")
    name = re.search(rb"(?m)^Name: ([^\r\n]+)$", metadata[0])
    version = re.search(rb"(?m)^Version: ([^\r\n]+)$", metadata[0])
    if name is None or version is None:
        raise ValueError(f"{path.name}: missing Python identity/version")
    return name.group(1).decode(), version.group(1).decode(), files


def verify(
    *, tag: str, commit: str, wheel: Path, facade: Path, native: Path, browser: Path
) -> dict[str, Any]:
    if re.fullmatch(r"[0-9a-f]{40}", commit) is None:
        raise ValueError("release commit must be a full lowercase Git SHA")
    npm_version = npm_version_from_tag(tag)
    python_version = tag.removeprefix("xyg-v")
    python_name, found_python, wheel_files = _wheel(wheel)
    if python_name != "xyg" or found_python != python_version:
        raise ValueError(
            f"Python wheel identity/version {python_name!r} {found_python!r} "
            f"does not match xyg {python_version!r}"
        )

    archives = {
        "facade": _read_tgz(facade),
        "native": _read_tgz(native),
        "browser": _read_tgz(browser),
    }
    for role, files in archives.items():
        try:
            package = json.loads(files["package/package.json"])
        except KeyError as error:
            raise ValueError(f"{role} package is missing package.json") from error
        if package.get("name") != EXPECTED[role] or package.get("version") != npm_version:
            raise ValueError(
                f"{role} identity/version mismatch: {package.get('name')!r} {package.get('version')!r}"
            )

    wheel_native = _only(wheel_files, "xyg/_native_lib/libxyg_core.so", "wheel native")
    node_native = _only(archives["native"], "package/libxyg_core.so", "Node native")
    if wheel_native != node_native:
        raise ValueError("Python wheel and Node package contain different libxyg_core.so bytes")
    wheel_client = _only(wheel_files, "xyg/static/standalone.js", "wheel standalone client")
    node_client = _only(
        archives["facade"], "package/client/standalone.js", "Node standalone client"
    )
    browser_client = _only(
        archives["browser"], "package/dist/standalone.js", "browser standalone client"
    )
    if len({wheel_client, node_client, browser_client}) != 1:
        raise ValueError("Python, Node, and browser packages contain different standalone.js bytes")

    manifest = json.loads(
        _only(archives["browser"], "package/ASSET-MANIFEST.json", "browser asset manifest")
    )
    if manifest.get("packageVersion") != npm_version:
        raise ValueError("browser asset manifest version does not match release cohort")
    assets = manifest.get("assets", {})
    if not isinstance(assets, dict) or set(assets) != EXPECTED_BROWSER_ASSETS:
        raise ValueError("browser asset manifest must list the exact four XYG assets")
    for name, expected in assets.items():
        if not isinstance(expected, dict):
            raise ValueError(f"browser asset manifest entry for {name} must be an object")
        payload = _only(archives["browser"], f"package/dist/{name}", f"browser asset {name}")
        if len(payload) != expected.get("bytes") or _digest(payload) != expected.get("sha256"):
            raise ValueError(f"browser asset manifest mismatch for {name}")

    paths = {"python": wheel, "nodeFacade": facade, "nodeNative": native, "browser": browser}
    return {
        "schemaVersion": 1,
        "releaseCommit": commit,
        "releaseTag": tag,
        "pythonVersion": python_version,
        "npmVersion": npm_version,
        "platform": "linux-x64",
        "sharedNativeSha256": _digest(wheel_native),
        "sharedStandaloneSha256": _digest(wheel_client),
        "artifacts": {
            key: {
                "file": path.name,
                "bytes": path.stat().st_size,
                "sha256": _digest(path.read_bytes()),
            }
            for key, path in paths.items()
        },
    }


def _only(files: dict[str, bytes], name: str, label: str) -> bytes:
    try:
        return files[name]
    except KeyError as error:
        raise ValueError(f"missing {label}: {name}") from error


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tag", required=True)
    parser.add_argument("--commit", required=True)
    parser.add_argument("--wheel", type=Path, required=True)
    parser.add_argument("--node-facade", type=Path, required=True)
    parser.add_argument("--node-native", type=Path, required=True)
    parser.add_argument("--browser", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        ledger = verify(
            tag=args.tag,
            commit=args.commit,
            wheel=args.wheel,
            facade=args.node_facade,
            native=args.node_native,
            browser=args.browser,
        )
        args.output.write_text(
            json.dumps(ledger, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
    except (
        OSError,
        ValueError,
        json.JSONDecodeError,
        tarfile.TarError,
        zipfile.BadZipFile,
    ) as error:
        print(f"XYG release cohort verification failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
