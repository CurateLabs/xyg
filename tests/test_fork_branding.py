"""Guard the fork's user-facing ownership and support pointers."""

from __future__ import annotations

import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
UPSTREAM_REPOSITORY = "reflex-dev" + "/xy"
UPSTREAM_DOCS = "reflex.dev/docs" + "/xy"
INTENTIONAL_PROVENANCE = {
    "CHANGELOG.md",
    "benchmarks/README.md",
    "benchmarks/launch_baselines/xy-0.1.0/macos-arm64-m5-pro/environment.json",
    "benchmarks/launch_baselines/xy-main-2026-07-26/macos-arm64-m5-pro/environment.json",
    "spec/README.md",
    "spec/design-dossier.md",
    "spec/design/host-neutral-architecture.md",
    "spec/design/xyg-naming.md",
    "spec/process/production-readiness.md",
    "tests/test_animation.py",
}


def _tracked_text() -> dict[str, str]:
    """Read every tracked UTF-8 text file without admitting build artifacts."""
    result = subprocess.run(
        ["git", "-C", str(ROOT), "ls-files", "-z"],
        check=True,
        capture_output=True,
    )
    text: dict[str, str] = {}
    for raw_path in result.stdout.split(b"\0"):
        if not raw_path:
            continue
        relative = raw_path.decode()
        try:
            text[relative] = (ROOT / relative).read_text()
        except UnicodeDecodeError:
            continue
    return text


def test_owned_files_route_users_to_curatelabs_except_documented_provenance() -> None:
    """Scan every tracked text file and permit upstream names only as history."""
    stale = {
        path
        for path, content in _tracked_text().items()
        if UPSTREAM_REPOSITORY in content or UPSTREAM_DOCS in content
    }

    assert stale == INTENTIONAL_PROVENANCE


def test_inherited_benchmark_repository_values_are_documented_provenance() -> None:
    """Preserve historical evidence while making its meaning explicit."""
    runbook = (ROOT / "benchmarks/README.md").read_text()
    baselines = sorted((ROOT / "benchmarks/launch_baselines").glob("*/**/environment.json"))

    assert "immutable provenance" in runbook
    assert baselines
    assert all(
        f"https://github.com/{UPSTREAM_REPOSITORY}" in path.read_text() for path in baselines
    )
