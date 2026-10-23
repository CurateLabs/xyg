#!/usr/bin/env python3
"""Classify whether changed paths require the complete release-surface matrix.

Fail-closed: a path is a release surface unless it is explicitly recognized prose
(root Markdown, LICENSE, ``docs/``, and ``spec/`` outside executable contracts).
Unknown paths therefore require the full matrix; they never skip it.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path

# Prose that no hard job reads. Everything else - including any path this list has never
# heard of, such as a new root tsconfig.json - is a release surface, so the classifier
# fails toward the complete matrix instead of silently skipping it (#1008).
# spec/abi/ and spec/wasm/ are generated-contract inputs to the native and WASM jobs.
PROSE_PREFIXES = ("docs/", "spec/")
CONTRACT_PREFIXES = ("spec/abi/", "spec/wasm/")
CONTRACT_FILES = {"spec/graphforge-compatibility.json"}
PROSE_ROOT_FILES = {"LICENSE"}
PROSE_ROOT_SUFFIXES = (".md",)


def is_release_surface(path: str) -> bool:
    normalized = path.strip().replace("\\", "/").removeprefix("./")
    if "/" not in normalized:
        prose = normalized in PROSE_ROOT_FILES or normalized.endswith(PROSE_ROOT_SUFFIXES)
    else:
        prose = (
            normalized.startswith(PROSE_PREFIXES)
            and not normalized.startswith(CONTRACT_PREFIXES)
            and normalized not in CONTRACT_FILES
        )
    return not prose


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
