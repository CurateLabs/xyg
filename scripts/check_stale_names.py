#!/usr/bin/env python3
"""Fail if current-product files still use retired XY/xy identities.

Enforces spec/design/xyg-naming.md, including the clean Python ``xyg``
namespace cutover. Historical audits, the naming matrix's old column, and the
one-way provenance migration script are file-allowlisted. Individual
intentional compatibility references use ``xyg-stale-name: allow``.
Stdlib only.
"""

from __future__ import annotations

import argparse
import ast
import io
import re
import sys
import tokenize
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parents[1]

SKIP_PARTS = {
    ".git",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".venv",
    ".web",
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
    Path("scripts/rename_fc_to_xy.py"),
    Path("scripts/check_stale_names.py"),
}

# Retired current-product identity. XYG_* names must not match these.
_ENV = r"(?<![A-Z0-9_])"
LINE_ALLOW_MARKER = "xyg-stale-name: allow"
NEEDLES = (
    ("python/xy package path", re.compile(r"python/xy(?:/|\b)")),
    ("xy wheel artifact", re.compile(r"(?<![A-Za-z0-9_])xy\.(?:whl|tar\.gz)\b")),
    ("xy artifact glob", re.compile(r"(?<![A-Za-z0-9_])xy-\*\.(?:whl|tar\.gz)\b")),
    ("pip show xy", re.compile(r"\bpip\s+show\s+xy\b")),
    (
        "backticked xy product noun",
        re.compile(r"`xy`\s+(?:release|content|distribution)\b", re.IGNORECASE),
    ),
    ("corrupted upstream XYG", re.compile(r"(?:upstream\s+XYG|reflex-dev/XYG)")),
    ("xy-native product wording", re.compile(r"(?<![A-Za-z0-9_])xy-native\b", re.IGNORECASE)),
    (
        "retired xy product description",
        re.compile(
            r"(?<![A-Za-z0-9_])(?:an?\s+)?xy(?=\s+(?:chart|package|wheel|dependency|distribution|install|engine|README)\b|\s*—\s*)",
            re.IGNORECASE,
        ),
    ),
    ("retired xy.pyplot label", re.compile(r"Matplotlib\s*\(xy\.pyplot\)")),
    ("retired xy benchmark target", re.compile(r"--packages\s+xy(?:,|\s|$)")),
    (
        "retired xy distribution constraint",
        re.compile(r"(?<![A-Za-z0-9_])xy(?:\[(?:reflex|dev)\]|==)"),
    ),
    ("user-facing xyg alias", re.compile(r"(?:^|[;])\s*import\s+xyg\s+as\s+xy\b")),
    (
        "premature xyg browser global",
        re.compile(r"(?<![A-Za-z0-9_])xyg\.(?:renderStandalone|decodeFrame|ChartView|markOf)\b"),
    ),
    ("current product XY brand", re.compile(r"(?<![A-Za-z0-9_])XY(?![A-Za-z0-9_])")),
    (
        "backticked xy Python API",
        re.compile(r"`xy\.(?!renderStandalone\b|decodeFrame\b)"),
    ),
    (
        "import xy",
        re.compile(r"(?:^|[\"';,])\s*(?:import|from)\s+xy(?:\s|\.|$)"),
    ),
    (
        "xy Python module reference",
        re.compile(r"(?<![A-Za-z0-9_])xy\.(?:kernels|widget|export)(?![A-Za-z0-9_])"),
    ),
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
    ("XY_BROWSER", re.compile(_ENV + r"XY_BROWSER\b")),
    ("XY_CHROMIUM", re.compile(_ENV + r"XY_CHROMIUM\b")),
    ("@xy/node", re.compile(r"['\"]@xy/node['\"]")),
    ("xy_abi_version", re.compile(r"(?<![A-Za-z0-9_])xy_abi_version\b")),
    ("lib.xy_ FFI", re.compile(r"(?<![A-Za-z0-9_])lib\.xy_[a-z]")),
    ("_lib.xy_ FFI", re.compile(r"_lib\.xy_[a-z]")),
    ("src/lib.rs ABI", re.compile(r"src/lib\.rs")),
)

_PYTHON_TEXT_XY = re.compile(r"(?<![A-Za-z0-9_])xy\.[A-Za-z_]")
_BROWSER_GLOBALS = ("xy.renderStandalone", "xy.decodeFrame")
_PRODUCT_DESCRIPTION_XY = re.compile(r"(?<![A-Za-z0-9_])xy(?=\.| chart\b| wheel\b| package\b|'s\b)")

_STRUCTURAL_CURRENT_IDENTITY = {
    "CLAUDE.md": (("retired repository heading", re.compile(r"^#\s+xy\s*/\s*xy\s*$", re.M)),),
    "CONTRIBUTING.md": (
        ("retired contributor heading", re.compile(r"^#\s+Contributing to xy\s*$", re.M)),
    ),
    "SECURITY.md": (("retired security product name", re.compile(r"^xy is\b", re.M)),),
    "MODULE.bazel": (("retired Bazel module name", re.compile(r'\bname\s*=\s*["\']xy["\']')),),
    "package.json": (
        ("retired root tool package name", re.compile(r'"name"\s*:\s*"xy-dev-tools"')),
    ),
    "package-lock.json": (
        ("retired root tool package name", re.compile(r'"name"\s*:\s*"xy-dev-tools"')),
    ),
    "docs/index.md": (
        ("retired documentation heading", re.compile(r"^#\s+What is `xy`\?\s*$", re.M)),
    ),
    "spec/process/production-readiness.md": (
        (
            "retired release product name",
            re.compile(r"(?m)^(?:This is the release bar for|xy is)\s+xy\b|^xy is\b"),
        ),
        ("retired release package path", re.compile(r"`xy/`|the `xy` package|`xy-<version>`")),
    ),
}

_WORKFLOW_INSTALL_XY = re.compile(r"(?m)^\s*-\s+name:\s+.*\bInstall xy\b", re.IGNORECASE)


def _python_text_errors(path: Path, rel: str, text: str, *, repository_scan: bool) -> list[str]:
    """Reject retired public Python names in comments, docstrings, and errors."""
    if path.suffix != ".py":
        return []
    if repository_scan and not rel.startswith(("python/xyg/", "python/reflex_xy/")):
        return []
    errors: list[str] = []
    try:
        tokens = tokenize.generate_tokens(io.StringIO(text).readline)
        for token in tokens:
            if token.type not in {tokenize.COMMENT, tokenize.STRING}:
                continue
            value = token.string
            if LINE_ALLOW_MARKER in value:
                continue
            for match in _PYTHON_TEXT_XY.finditer(value):
                if value.startswith(_BROWSER_GLOBALS, match.start()):
                    continue
                errors.append(
                    f"{rel}:{token.start[0]}: stale xy Python public reference: {value.strip()}"
                )
                break
    except (IndentationError, SyntaxError, tokenize.TokenError):
        pass
    return errors


def _module_description_errors(path: Path, rel: str, text: str) -> list[str]:
    """Reject ambiguous XYG product/API wording in current developer surfaces."""
    if path.suffix != ".py" or not rel.startswith(("scripts/", "benchmarks/", "examples/")):
        return []
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return []
    doc = ast.get_docstring(tree, clean=False)
    if not doc or LINE_ALLOW_MARKER in doc:
        return []
    matches = [
        match
        for match in _PRODUCT_DESCRIPTION_XY.finditer(doc)
        if not doc.startswith(_BROWSER_GLOBALS, match.start())
    ]
    if not matches:
        return []
    lineno = tree.body[0].lineno if tree.body else 1
    return [f"{rel}:{lineno}: stale XYG product/API wording in module description"]


def _structural_identity_errors(rel: str, text: str) -> list[str]:
    """Lock high-impact repository, build, release, and workflow identity surfaces."""
    errors: list[str] = []
    for label, pattern in _STRUCTURAL_CURRENT_IDENTITY.get(rel, ()):
        for match in pattern.finditer(text):
            lineno = text.count("\n", 0, match.start()) + 1
            line = text.splitlines()[lineno - 1]
            if LINE_ALLOW_MARKER in line:
                continue
            errors.append(f"{rel}:{lineno}: stale {label}")
    if rel.startswith(".github/workflows/"):
        for match in _WORKFLOW_INSTALL_XY.finditer(text):
            lineno = text.count("\n", 0, match.start()) + 1
            line = text.splitlines()[lineno - 1]
            if LINE_ALLOW_MARKER in line:
                continue
            errors.append(f"{rel}:{lineno}: stale workflow product label")
    return errors


def _skip(path: Path) -> bool:
    return any(part in SKIP_PARTS for part in path.parts)


def _should_scan(path: Path) -> bool:
    if _skip(path) or not path.is_file():
        return False
    rel = path.relative_to(ROOT).as_posix() if path.is_relative_to(ROOT) else path.as_posix()
    if rel.startswith(("assets/external/", "docs/app/assets/external/", "python/xyg/static/")):
        return False
    if path.name in SCAN_NAMES:
        return True
    return path.suffix in SCAN_SUFFIXES


def _allowed_src_lib_rs(line: str, start: int) -> bool:
    prefix = line[:start]
    return (
        prefix.endswith("crates/xyg-core/")
        or prefix.endswith("crates/xyg-engine/")
        or prefix.endswith("crates/xyg-wasm/")
        or prefix.endswith("js/")
        or "/crates/xyg-core/" in prefix[-40:]
        or "/crates/xyg-engine/" in prefix[-40:]
        or "/crates/xyg-wasm/" in prefix[-40:]
    )


def _allowed_xy_node(line: str) -> bool:
    return "never publish" in line.lower()


def _allowed_provenance_xy(line: str) -> bool:
    """Allow only explicit upstream/history identifiers, never current branding."""
    return bool(
        "XY-vs-XYG" in line
        or "upstream XY" in line
        or ("reflex-dev/" + "xy") in line
        or re.search(r"\bXY-(?:SEC|CI|PERF)-", line)
    )


_HISTORICAL_IDENTITY_ALLOWLIST = {
    ("spec/process/perf-audit-2026-07-22.md", "libxy_core"),
    ("spec/process/security-audit-2026-07-06.md", "XY_REQUIRE_CARGO"),
    ("spec/process/security-audit-2026-07-06.md", "XY_NATIVE_LIB"),
}

_NEGATIVE_TEST_LINE_FRAGMENTS = (
    "libxy_core",
    "XY_NATIVE_LIB",
    "XY_BROWSER",
    "XY_CHROMIUM",
    "import xy",
    "python/xy",
    "xy Python module reference",
    "xy.whl",
    "xy wheel artifact",
    "`xy.legend",
    "backticked xy Python API",
    "xy-*.whl",
    "xy-*.tar.gz",
    "pip show xy",
    "upstream XYG",
    "reflex-dev/XYG",
    "corrupted upstream XYG",
    "xy-native",
    "xy package",
    "xy dependency",
    "--packages xy",
    "xy[reflex]",
    "retired xy distribution constraint",
    "Build an XY chart",
    "import xyg as xy",
    "current product XY brand",
    "src/lib.rs ABI",
    "ABI_VERSION in src/lib.rs",
)


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
    repository_scan = root.resolve() == ROOT.resolve()
    for path in iter_scan_files(root):
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        rel = path.relative_to(root).as_posix()
        errors.extend(_structural_identity_errors(rel, text))
        errors.extend(_python_text_errors(path, rel, text, repository_scan=repository_scan))
        if repository_scan:
            errors.extend(_module_description_errors(path, rel, text))
        for lineno, line in enumerate(text.splitlines(), 1):
            if LINE_ALLOW_MARKER in line:
                continue
            if rel == "tests/test_stale_names.py" and any(
                fragment in line for fragment in _NEGATIVE_TEST_LINE_FRAGMENTS
            ):
                continue
            for label, pattern in NEEDLES:
                for match in pattern.finditer(line):
                    if label == "src/lib.rs ABI" and _allowed_src_lib_rs(line, match.start()):
                        continue
                    if label == "@xy/node" and _allowed_xy_node(line):
                        continue
                    if (rel, label) in _HISTORICAL_IDENTITY_ALLOWLIST:
                        continue
                    if label == "current product XY brand" and (
                        _allowed_provenance_xy(line) or "f64 XY" in line
                    ):
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
        print(
            "Use XYG/xyg for the current product and package. Retain xy only for "
            "explicitly documented browser protocol, coordinates, provenance, or "
            f"history; otherwise migrate it or annotate the intentional line with {LINE_ALLOW_MARKER!r}.",
            file=sys.stderr,
        )
        return 1
    print("stale-name gate ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
