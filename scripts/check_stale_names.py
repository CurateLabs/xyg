#!/usr/bin/env python3
"""Fail if current-product files still use retired XY native identity.

Enforces spec/design/xyg-naming.md for the crate-split identifiers that
have already landed: libxyg_core, XYG_* env vars, @curatelabs/xyg-node,
and crates/xyg-core/src/lib.rs as the ABI location. Historical audits,
the naming matrix (old column), and provenance scripts are allowlisted.
Stdlib only.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parents[1]

SKIP_PARTS = {
    ".git",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".venv",
    "__pycache__",
    "dist",
    "node_modules",
    "target",
    "wheelhouse",
}

SCAN_NAMES = {
    "AGENTS.md",
    "BUILD.bazel",
    "CLAUDE.md",
    "CONTRIBUTING.md",
    "Dockerfile",
    "Makefile",
    "postBuild",
}

SCAN_SUFFIXES = {
    ".Dockerfile",
    ".bazel",
    ".js",
    ".json",
    ".md",
    ".mjs",
    ".py",
    ".rs",
    ".sh",
    ".toml",
    ".ts",
    ".yml",
    ".yaml",
}

ALLOWLIST_FILES = {
    Path("spec/design/xyg-naming.md"),
    Path("CHANGELOG.md"),
    Path("spec/process/perf-audit-2026-07-22.md"),
    Path("spec/process/security-audit-2026-07-06.md"),
    Path("scripts/rename_fc_to_xy.py"),
    Path("scripts/check_stale_names.py"),
    Path("tests/test_stale_names.py"),
}

# Retired current-product identity. XYG_* names must not match these.
_ENV = r"(?<![A-Z0-9_])"
NEEDLES = (
    ("libxy_core", re.compile(r"libxy_core")),
    ("xy_core.dll", re.compile(r"(?<![A-Za-z0-9_])xy_core\.dll")),
    ("XY_NATIVE_LIB", re.compile(_ENV + r"XY_NATIVE_LIB\b")),
    ("XY_SKIP_CARGO", re.compile(_ENV + r"XY_SKIP_CARGO\b")),
    ("XY_REQUIRE_CARGO", re.compile(_ENV + r"XY_REQUIRE_CARGO\b")),
    ("XY_SKIP_NODE", re.compile(_ENV + r"XY_SKIP_NODE\b")),
    ("XY_CARGO_TARGET", re.compile(_ENV + r"XY_CARGO_TARGET\b")),
    ("XY_WHEEL_PLATFORM", re.compile(_ENV + r"XY_WHEEL_PLATFORM\b")),
    ("XY_ALLOW_PYPI_PUBLISH", re.compile(_ENV + r"XY_ALLOW_PYPI_PUBLISH\b")),
    ("XY_SIMD", re.compile(_ENV + r"XY_SIMD\b")),
    ("XY_EXPECTED_ABI", re.compile(_ENV + r"XY_EXPECTED_ABI\b")),
    ("@xy/node", re.compile(r"['\"]@xy/node['\"]")),
    ("xy_abi_version", re.compile(r"(?<![A-Za-z0-9_])xy_abi_version\b")),
    ("lib.xy_ FFI", re.compile(r"(?<![A-Za-z0-9_])lib\.xy_[a-z]")),
    ("_lib.xy_ FFI", re.compile(r"_lib\.xy_[a-z]")),
    ("src/lib.rs ABI", re.compile(r"src/lib\.rs")),
)


def _skip(path: Path) -> bool:
    return any(part in SKIP_PARTS for part in path.parts)


def _should_scan(path: Path) -> bool:
    if _skip(path) or not path.is_file():
        return False
    if path.name in SCAN_NAMES:
        return True
    return path.suffix in SCAN_SUFFIXES


def _allowed_src_lib_rs(line: str, start: int) -> bool:
    prefix = line[:start]
    return (
        prefix.endswith("crates/xyg-core/")
        or prefix.endswith("crates/xyg-engine/")
        or prefix.endswith("js/")
        or "/crates/xyg-core/" in prefix[-40:]
        or "/crates/xyg-engine/" in prefix[-40:]
    )


def _allowed_xy_node(line: str) -> bool:
    return "never publish" in line.lower()


def iter_scan_files(root: Path) -> list[Path]:
    files = []
    for path in root.rglob("*"):
        if not _should_scan(path):
            continue
        rel = path.relative_to(root)
        if rel in ALLOWLIST_FILES:
            continue
        files.append(path)
    return sorted(files)


def check_stale_names(root: Path = ROOT) -> list[str]:
    errors: list[str] = []
    for path in iter_scan_files(root):
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        rel = path.relative_to(root).as_posix()
        for lineno, line in enumerate(text.splitlines(), 1):
            for label, pattern in NEEDLES:
                for match in pattern.finditer(line):
                    if label == "src/lib.rs ABI" and _allowed_src_lib_rs(line, match.start()):
                        continue
                    if label == "@xy/node" and _allowed_xy_node(line):
                        continue
                    errors.append(f"{rel}:{lineno}: stale {label}: {line.strip()}")
    return errors


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", nargs="?", type=Path, default=ROOT)
    args = parser.parse_args(argv)
    errors = check_stale_names(args.root)
    if errors:
        for error in errors:
            print(error, file=sys.stderr)
        print(f"{len(errors)} stale XY identity name(s)", file=sys.stderr)
        return 1
    print("stale-name gate ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
