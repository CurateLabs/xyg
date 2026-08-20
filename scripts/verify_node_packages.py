#!/usr/bin/env python3
"""Verify @curatelabs/xyg-node exact-platform package inventory (#52).

Stdlib-only gate that runs without npm registry credentials. Checks:

- Facade optionalDependencies match the five exact-platform packages
- Each platform package declares the correct name / os / cpu / files / exports
- Source trees contain no CDN URLs, system library paths, or Python-static paths
- Optional staged natives stay under a size budget and match the expected basename
- Emits a SHA-256 inventory of package.json, index/entry sources, and natives

Examples:
  python3 scripts/verify_node_packages.py
  python3 scripts/verify_node_packages.py --write /tmp/xyg-node-inventory.json
  python3 scripts/verify_node_packages.py --require-native
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
PACKAGES = REPO_ROOT / "packages"
FACADE_DIR = PACKAGES / "xy-node"

# Exact matrix mirrored by packages/xy-node/src/native-path.js PLATFORM_PACKAGES.
PLATFORM_PACKAGES: dict[str, dict[str, Any]] = {
    "darwin-arm64": {
        "name": "@curatelabs/xyg-node-darwin-arm64",
        "dir": "xyg-node-darwin-arm64",
        "os": ["darwin"],
        "cpu": ["arm64"],
        "lib": "libxyg_core.dylib",
    },
    "darwin-x64": {
        "name": "@curatelabs/xyg-node-darwin-x64",
        "dir": "xyg-node-darwin-x64",
        "os": ["darwin"],
        "cpu": ["x64"],
        "lib": "libxyg_core.dylib",
    },
    "linux-x64": {
        "name": "@curatelabs/xyg-node-linux-x64",
        "dir": "xyg-node-linux-x64",
        "os": ["linux"],
        "cpu": ["x64"],
        "lib": "libxyg_core.so",
    },
    "linux-arm64": {
        "name": "@curatelabs/xyg-node-linux-arm64",
        "dir": "xyg-node-linux-arm64",
        "os": ["linux"],
        "cpu": ["arm64"],
        "lib": "libxyg_core.so",
    },
    "win32-x64": {
        "name": "@curatelabs/xyg-node-win32-x64",
        "dir": "xyg-node-win32-x64",
        "os": ["win32"],
        "cpu": ["x64"],
        "lib": "xyg_core.dll",
    },
}

# Source-only budgets (natives are measured separately when staged).
FACADE_SOURCE_BUDGET_BYTES = 8 * 1024 * 1024
PLATFORM_SOURCE_BUDGET_BYTES = 64 * 1024
NATIVE_BUDGET_BYTES = 40 * 1024 * 1024

FORBIDDEN_PATTERNS = (
    re.compile(r"cdn\.jsdelivr\.net", re.I),
    re.compile(r"unpkg\.com", re.I),
    re.compile(r"cdnjs\.cloudflare\.com", re.I),
    re.compile(r"/usr/lib"),
    re.compile(r"/usr/local/lib"),
    re.compile(r"python/xy/static"),
    re.compile(r"LD_LIBRARY_PATH"),
    re.compile(r"DYLD_LIBRARY_PATH"),
)

SCAN_SUFFIXES = {".js", ".mjs", ".cjs", ".ts", ".json", ".md"}
SKIP_DIRS = {"node_modules", ".git", "_native_lib"}


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _tree_bytes(root: Path, *, exclude_names: set[str] | None = None) -> int:
    exclude = exclude_names or set()
    total = 0
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if any(part in SKIP_DIRS or part in exclude for part in path.parts):
            continue
        if path.name in {
            "libxyg_core.so",
            "libxyg_core.dylib",
            "xyg_core.dll",
        }:
            continue
        total += path.stat().st_size
    return total


def _scan_forbidden(root: Path) -> list[str]:
    hits: list[str] = []
    paths = [root] if root.is_file() else list(root.rglob("*"))
    for path in paths:
        if not path.is_file():
            continue
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        if path.suffix not in SCAN_SUFFIXES:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for pattern in FORBIDDEN_PATTERNS:
            if pattern.search(text):
                rel = path.relative_to(REPO_ROOT) if path.is_relative_to(REPO_ROOT) else path
                hits.append(f"{rel}: matches {pattern.pattern}")
    return hits


def verify(*, require_native: bool = False) -> dict[str, Any]:
    errors: list[str] = []
    inventory: dict[str, Any] = {
        "facade": {},
        "platforms": {},
        "license": str((REPO_ROOT / "LICENSE").relative_to(REPO_ROOT)),
    }

    facade_pkg_path = FACADE_DIR / "package.json"
    if not facade_pkg_path.is_file():
        raise SystemExit(f"missing facade package.json: {facade_pkg_path}")
    facade = _load_json(facade_pkg_path)
    if facade.get("name") != "@curatelabs/xyg-node":
        errors.append(f"facade name must be @curatelabs/xyg-node, got {facade.get('name')!r}")

    optional = facade.get("optionalDependencies") or {}
    expected_names = {meta["name"] for meta in PLATFORM_PACKAGES.values()}
    if set(optional) != expected_names:
        errors.append(
            "facade optionalDependencies mismatch: "
            f"got {sorted(optional)} expected {sorted(expected_names)}"
        )

    hits = _scan_forbidden(FACADE_DIR / "src")
    errors.extend(hits)

    for _plat_id, meta in PLATFORM_PACKAGES.items():
        name = meta["name"]
        expected_file = f"file:../{meta['dir']}"
        if optional.get(name) != expected_file:
            errors.append(
                f"optionalDependency {name} must be {expected_file!r}, got {optional.get(name)!r}"
            )

    facade_bytes = _tree_bytes(FACADE_DIR, exclude_names={"package-lock.json"})
    if facade_bytes > FACADE_SOURCE_BUDGET_BYTES:
        errors.append(
            f"facade source exceeds budget: {facade_bytes} > {FACADE_SOURCE_BUDGET_BYTES}"
        )
    inventory["facade"] = {
        "name": facade.get("name"),
        "version": facade.get("version"),
        "package_json_sha256": _sha256(facade_pkg_path),
        "source_bytes": facade_bytes,
        "source_budget_bytes": FACADE_SOURCE_BUDGET_BYTES,
        "optionalDependencies": optional,
    }

    for plat_id, meta in sorted(PLATFORM_PACKAGES.items()):
        pkg_dir = PACKAGES / meta["dir"]
        pkg_json_path = pkg_dir / "package.json"
        index_path = pkg_dir / "index.js"
        entry: dict[str, Any] = {"id": plat_id, "name": meta["name"]}
        if not pkg_json_path.is_file():
            errors.append(f"missing platform package.json: {pkg_json_path}")
            inventory["platforms"][plat_id] = entry
            continue
        pkg = _load_json(pkg_json_path)
        if pkg.get("name") != meta["name"]:
            errors.append(f"{plat_id}: name {pkg.get('name')!r} != {meta['name']!r}")
        if pkg.get("os") != meta["os"]:
            errors.append(f"{plat_id}: os {pkg.get('os')!r} != {meta['os']!r}")
        if pkg.get("cpu") != meta["cpu"]:
            errors.append(f"{plat_id}: cpu {pkg.get('cpu')!r} != {meta['cpu']!r}")
        files = pkg.get("files") or []
        for required in ("index.js", meta["lib"], "README.md"):
            if required not in files:
                errors.append(f"{plat_id}: files missing {required!r}")
        exports = pkg.get("exports") or {}
        if exports.get("./package.json") != "./package.json":
            errors.append(f"{plat_id}: exports must include ./package.json")
        if not index_path.is_file():
            errors.append(f"{plat_id}: missing index.js")

        source_bytes = _tree_bytes(pkg_dir)
        if source_bytes > PLATFORM_SOURCE_BUDGET_BYTES:
            errors.append(
                f"{plat_id}: source exceeds budget: {source_bytes} > {PLATFORM_SOURCE_BUDGET_BYTES}"
            )

        lib_path = pkg_dir / meta["lib"]
        native: dict[str, Any] | None = None
        if lib_path.is_file():
            size = lib_path.stat().st_size
            if size > NATIVE_BUDGET_BYTES:
                errors.append(f"{plat_id}: native exceeds budget: {size} > {NATIVE_BUDGET_BYTES}")
            native = {
                "path": str(lib_path.relative_to(REPO_ROOT)),
                "bytes": size,
                "sha256": _sha256(lib_path),
                "budget_bytes": NATIVE_BUDGET_BYTES,
            }
        elif require_native:
            errors.append(f"{plat_id}: required native missing at {lib_path}")

        errors.extend(_scan_forbidden(pkg_dir / "index.js"))
        errors.extend(_scan_forbidden(pkg_json_path))

        entry.update(
            {
                "version": pkg.get("version"),
                "package_json_sha256": _sha256(pkg_json_path),
                "index_sha256": _sha256(index_path) if index_path.is_file() else None,
                "source_bytes": source_bytes,
                "source_budget_bytes": PLATFORM_SOURCE_BUDGET_BYTES,
                "native": native,
            }
        )
        inventory["platforms"][plat_id] = entry

    inventory["errors"] = errors
    inventory["ok"] = not errors
    return inventory


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--write",
        type=Path,
        help="write the inventory JSON (hashes + budgets) to this path",
    )
    parser.add_argument(
        "--require-native",
        action="store_true",
        help="fail when platform packages lack a staged native library",
    )
    args = parser.parse_args(argv)
    inventory = verify(require_native=args.require_native)
    text = json.dumps(inventory, indent=2, sort_keys=True) + "\n"
    if args.write:
        args.write.parent.mkdir(parents=True, exist_ok=True)
        args.write.write_text(text, encoding="utf-8")
        print(f"wrote {args.write}")
    else:
        sys.stdout.write(text)
    if inventory["errors"]:
        for err in inventory["errors"]:
            print(f"ERROR: {err}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
