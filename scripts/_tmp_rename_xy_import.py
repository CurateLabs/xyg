#!/usr/bin/env python3
"""One-shot mechanical rewrite for #51: import/path xy → xyg.

Not a product tool — delete after the cutover PR. Skips historical allowlists
and frozen baselines. Does not touch deferred browser branding (window.xy,
class=xy) or reflex_xy.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

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
    "launch_baselines",
}

SKIP_FILES = {
    Path("scripts/_tmp_rename_xy_import.py"),
    Path("scripts/rename_fc_to_xy.py"),
    Path("spec/design/xyg-naming.md"),  # matrix Old column must keep xy
    Path("CHANGELOG.md"),
    Path("spec/process/security-audit-2026-07-06.md"),
    Path("spec/process/perf-audit-2026-07-22.md"),
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

SCAN_NAMES = {
    "AGENTS.md",
    "BUILD.bazel",
    "CLAUDE.md",
    "CONTRIBUTING.md",
    "Dockerfile",
    "Makefile",
    "postBuild",
}


def _skip(path: Path) -> bool:
    if any(part in SKIP_PARTS for part in path.parts):
        return True
    try:
        rel = path.relative_to(ROOT)
    except ValueError:
        return True
    return rel in SKIP_FILES


def _should_scan(path: Path) -> bool:
    if _skip(path) or not path.is_file():
        return False
    if path.name in SCAN_NAMES:
        return True
    return path.suffix in SCAN_SUFFIXES


def rewrite(text: str) -> str:
    out = text
    # Paths.
    out = re.sub(r"python/xy\b", "python/xyg", out)
    out = re.sub(r'(["\'])xy/(_native|static|__)', r"\1xyg/\2", out)
    out = re.sub(r'(["\'])xy/', r"\1xyg/", out)
    # Path / join segments: "python" / "xy" and "python", "xy"
    out = re.sub(
        r'(["\'])python(["\'])\s*/\s*(["\'])xy(["\'])',
        r"\1python\2 / \3xyg\4",
        out,
    )
    out = re.sub(
        r'(["\'])python(["\'])\s*,\s*(["\'])xy(["\'])',
        r"\1python\2, \3xyg\4",
        out,
    )
    # importlib / string module loads (exact package or dotted).
    out = re.sub(
        r'(import(?:lib\.import_module|orskip)|__import__)\(\s*(["\'])xy\2(\s*\))',
        r"\1(\2xyg\2\3",
        out,
    )
    out = re.sub(
        r'(import(?:lib\.import_module|orskip)|__import__)\(\s*(["\'])xy\.',
        r"\1(\2xyg.",
        out,
    )
    # Ruff known-first-party.
    out = re.sub(
        r'(known-first-party\s*=\s*\[[^\]]*["\'])xy(["\'])',
        r"\1xyg\2",
        out,
    )
    # Imports — \b prevents matching xyg / xyz / reflex_xy.
    out = re.sub(r"\bfrom xy\.", "from xyg.", out)
    out = re.sub(r"\bfrom xy import\b", "from xyg import", out)
    out = re.sub(r"\bimport xy\b", "import xyg", out)
    return out


def main() -> int:
    changed = 0
    for path in sorted(ROOT.rglob("*")):
        if not _should_scan(path):
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        new = rewrite(text)
        if new != text:
            path.write_text(new, encoding="utf-8")
            changed += 1
            print(path.relative_to(ROOT))
    print(f"rewrote {changed} files", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
