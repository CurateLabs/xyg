#!/usr/bin/env python3
"""Stage the immutable, offline @curatelabs/xyg browser release package."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import sys
from pathlib import Path

try:
    from stage_node_packages import (
        PUBLISH_CONFIG,
        REPOSITORY,
        SEMVER_RE,
        npm_version_from_tag,
    )
except ModuleNotFoundError:
    from scripts.stage_node_packages import (
        PUBLISH_CONFIG,
        REPOSITORY,
        SEMVER_RE,
        npm_version_from_tag,
    )

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "packages" / "xy-client"
PACKAGE_NAME = "@curatelabs/xyg"
ASSETS = ("index.js", "standalone.js", "wasm-worker.js", "xyg-wasm.wasm")
EXPECTED_EXPORTS = {
    ".": "./dist/index.js",
    "./standalone": "./dist/standalone.js",
    "./wasm-worker": "./dist/wasm-worker.js",
    "./xyg-wasm.wasm": "./dist/xyg-wasm.wasm",
}
JS_BUDGET_BYTES = 4 * 1024 * 1024
WASM_BUDGET_BYTES = 8 * 1024 * 1024
TOTAL_BUDGET_BYTES = 12 * 1024 * 1024
FORBIDDEN_JS = (
    b"//unpkg.com",
    b"//cdn.jsdelivr.net",
    b"python/xyg/static",
    b"node_modules/",
    b"target/wasm32",
    b"@xy/",
)
ALLOWED_NAMESPACE_URLS = {
    "http://www.w3.org/1999/xhtml",
    "http://www.w3.org/2000/svg",
}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _contract() -> dict[str, int]:
    wasm = json.loads((ROOT / "spec" / "wasm" / "abi.json").read_text(encoding="utf-8"))
    header = (ROOT / "js" / "src" / "00_header.ts").read_text(encoding="utf-8")
    protocol = re.search(r"export const PROTOCOL = (\d+);", header)
    if protocol is None:
        raise ValueError("cannot determine XYG browser wire protocol version")
    return {
        "wireProtocolVersion": int(protocol.group(1)),
        "wasmAbiVersion": int(wasm["abi_version"]),
        "sceneVersion": int(wasm["scene_version"]),
        "painterVersion": int(wasm["painter_version"]),
    }


def _validate_assets(dist: Path) -> dict[str, dict[str, int | str]]:
    if not dist.is_dir():
        raise ValueError(f"browser dist directory is missing: {dist}")
    symlinks = sorted(path.name for path in dist.iterdir() if path.is_symlink())
    if symlinks:
        raise ValueError(f"browser dist assets must not be symlinks: {symlinks!r}")
    actual = sorted(path.name for path in dist.iterdir() if path.is_file())
    if actual != sorted(ASSETS):
        raise ValueError(
            f"browser dist inventory must be exactly {list(ASSETS)!r}; found {actual!r}"
        )

    inventory: dict[str, dict[str, int | str]] = {}
    total = 0
    for name in ASSETS:
        path = dist / name
        size = path.stat().st_size
        if size <= 0:
            raise ValueError(f"browser asset {name} is empty")
        total += size
        if name.endswith(".js"):
            if size > JS_BUDGET_BYTES:
                raise ValueError(f"browser asset {name} exceeds {JS_BUDGET_BYTES} byte JS budget")
            payload = path.read_bytes()
            urls = set(re.findall(rb"https?://[A-Za-z0-9._~:/?#\[\]@!$&()*+,;=%-]+", payload))
            remote_urls = {
                value.decode("ascii")
                for value in urls
                if value.decode("ascii") not in ALLOWED_NAMESPACE_URLS
            }
            if remote_urls:
                raise ValueError(
                    f"browser asset {name} contains forbidden network URL {sorted(remote_urls)[0]}"
                )
            forbidden = next((item for item in FORBIDDEN_JS if item in payload), None)
            if forbidden is not None:
                raise ValueError(
                    f"browser asset {name} contains forbidden offline reference "
                    f"{forbidden.decode('ascii')}"
                )
        elif size > WASM_BUDGET_BYTES:
            raise ValueError(f"browser WASM exceeds {WASM_BUDGET_BYTES} byte budget")
        inventory[name] = {"bytes": size, "sha256": _sha256(path)}
    if not (dist / "xyg-wasm.wasm").read_bytes().startswith(b"\0asm\x01\0\0\0"):
        raise ValueError("browser WASM asset has an invalid module header")
    if total > TOTAL_BUDGET_BYTES:
        raise ValueError(f"browser assets exceed {TOTAL_BUDGET_BYTES} byte package budget")
    return inventory


def stage(*, dist: Path, output: Path, version: str) -> Path:
    if SEMVER_RE.fullmatch(version) is None:
        raise ValueError(f"invalid npm semver {version!r}")
    inventory = _validate_assets(dist)
    destination = output / "xyg-browser"
    if destination.exists():
        shutil.rmtree(destination)
    (destination / "dist").mkdir(parents=True)
    for name in ASSETS:
        shutil.copy2(dist / name, destination / "dist" / name)
    for name in ("README.md", "NOTICE"):
        shutil.copy2(SOURCE / name, destination / name)
    shutil.copy2(ROOT / "LICENSE", destination / "LICENSE")

    manifest = json.loads((SOURCE / "package.json").read_text(encoding="utf-8"))
    if manifest.get("name") != PACKAGE_NAME:
        raise ValueError(
            f"browser package identity must be {PACKAGE_NAME}, got {manifest.get('name')!r}"
        )
    if manifest.get("type") != "module" or manifest.get("exports") != EXPECTED_EXPORTS:
        raise ValueError(
            "browser package must expose only the canonical XYG ESM/IIFE/Worker/WASM paths"
        )
    if manifest.get("sideEffects") is not False:
        raise ValueError("browser package must declare sideEffects=false")
    if manifest.get("scripts"):
        raise ValueError(f"{PACKAGE_NAME} must not declare npm lifecycle scripts")
    if manifest.get("bin"):
        raise ValueError(f"{PACKAGE_NAME} must not declare executable package bins")
    manifest.pop("private", None)
    manifest["version"] = version
    manifest["repository"] = REPOSITORY
    manifest["publishConfig"] = PUBLISH_CONFIG
    manifest["files"] = ["dist", "ASSET-MANIFEST.json", "README.md", "NOTICE", "LICENSE"]
    for dependency_field in ("dependencies", "optionalDependencies", "peerDependencies"):
        if manifest.get(dependency_field):
            raise ValueError(f"{PACKAGE_NAME} must remain runtime-dependency-free")
    (destination / "package.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )
    asset_manifest = {
        "schemaVersion": 1,
        "package": PACKAGE_NAME,
        "packageVersion": version,
        **_contract(),
        "assets": inventory,
    }
    (destination / "ASSET-MANIFEST.json").write_text(
        json.dumps(asset_manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return destination


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    version = parser.add_mutually_exclusive_group(required=True)
    version.add_argument("--tag")
    version.add_argument("--version")
    parser.add_argument("--dist", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        release_version = npm_version_from_tag(args.tag) if args.tag else args.version
        stage(dist=args.dist, output=args.output, version=release_version)
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f"XYG browser package staging failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
