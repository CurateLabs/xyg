"""Guard the fork's user-facing ownership and support pointers."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
UPSTREAM_REPOSITORY = "github.com/reflex-dev/xy"


def test_owned_documentation_does_not_route_users_to_upstream() -> None:
    """Keep source, support, CI, and security links on CurateLabs/xyg."""
    paths = [
        ROOT / "README.md",
        ROOT / "CONTRIBUTING.md",
        ROOT / "SECURITY.md",
        ROOT / "python/xy/pyplot/_translate.py",
        ROOT / "docs/app/xy_docs/footer.py",
        ROOT / "docs/app/xy_docs/navbar.py",
        ROOT / "docs/app/xy_docs/xy_docs.py",
        *sorted((ROOT / "docs").rglob("*.md")),
    ]

    stale = [
        str(path.relative_to(ROOT)) for path in paths if UPSTREAM_REPOSITORY in path.read_text()
    ]

    assert stale == []


def test_inherited_benchmark_repository_values_are_documented_provenance() -> None:
    """Preserve historical evidence while making its meaning explicit."""
    runbook = (ROOT / "benchmarks/README.md").read_text()
    baselines = sorted((ROOT / "benchmarks/launch_baselines").glob("*/**/environment.json"))

    assert "immutable provenance" in runbook
    assert baselines
    assert all("https://github.com/reflex-dev/xy" in path.read_text() for path in baselines)
