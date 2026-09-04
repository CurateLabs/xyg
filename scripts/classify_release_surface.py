#!/usr/bin/env python3
"""Classify whether changed paths require the complete release-surface matrix."""

from __future__ import annotations

import argparse
import os
from pathlib import Path

RELEASE_PREFIXES = (
    ".github/workflows/",
    ".codspeed/",
    "benchmarks/",
    "crates/",
    "js/",
    "packages/",
    "python/",
    "scripts/",
    "spec/abi/",
    "tests/",
)
RELEASE_FILES = {
    ".github/CODEOWNERS",
    "Cargo.lock",
    "Cargo.toml",
    "Makefile",
    "hatch_build.py",
    "package-lock.json",
    "package.json",
    "pyproject.toml",
    "rust-toolchain.toml",
    "uv.lock",
}


def is_release_surface(path: str) -> bool:
    normalized = path.strip().replace("\\", "/").removeprefix("./")
    return normalized in RELEASE_FILES or normalized.startswith(RELEASE_PREFIXES)


def classify(paths: list[str]) -> bool:
    return any(is_release_surface(path) for path in paths)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="*")
    parser.add_argument("--github-output", type=Path)
    args = parser.parse_args()
    paths = args.paths or [line for line in os.sys.stdin.read().splitlines() if line.strip()]
    required = classify(paths)
    value = str(required).lower()
    if args.github_output is not None:
        with args.github_output.open("a", encoding="utf-8") as output:
            output.write(f"required={value}\n")
    print(value)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
