from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest


def _load():
    path = Path(__file__).resolve().parents[1] / "scripts" / "release_version.py"
    spec = importlib.util.spec_from_file_location("release_version", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


rv = _load()

CASES = [
    # (canonical tag, npm, python)
    ("xyg-v0.6.0", "0.6.0", "0.6.0"),
    ("xyg-v0.6.0-rc.5", "0.6.0-rc.5", "0.6.0rc5"),
    ("xyg-v0.6.0-alpha.1", "0.6.0-alpha.1", "0.6.0a1"),
    ("xyg-v0.6.0-beta.12", "0.6.0-beta.12", "0.6.0b12"),
    ("xyg-v10.20.30-rc.0", "10.20.30-rc.0", "10.20.30rc0"),
]


@pytest.mark.parametrize(("tag", "npm", "python"), CASES)
def test_canonical_tag_round_trips_across_ecosystems(tag: str, npm: str, python: str) -> None:
    release = rv.parse_tag(tag)
    assert (release.npm, release.python, release.tag) == (npm, python, tag)
    assert rv.parse_npm(npm) == release
    assert rv.parse_python(python) == release
    assert rv.require_cohort(tag=tag, python=python, npm=npm) == release


@pytest.mark.parametrize(("tag", "npm", "python"), CASES)
def test_legacy_pep440_tag_names_the_same_release(tag: str, npm: str, python: str) -> None:
    assert rv.parse_tag("xyg-v" + python) == rv.parse_tag(tag)


@pytest.mark.parametrize(
    "tag",
    [
        "xyg-v0.6.0.dev1",
        "xyg-v0.6.0.dev1+gabc123",
        "xyg-v0.6.0.post1",
        "xyg-v0.6.0+local",
        "xyg-v0.6.0-rc",
        "xyg-v0.6.0-rc.",
        "xyg-v0.6.0-rc.05",
        "xyg-v0.6.0-rc5",
        "xyg-v0.6.0-RC.5",
        "xyg-v0.6.0-rc.5.1",
        "xyg-v0.6.0-rc.5+build",
        "xyg-v0.6.0-alpha1",
        "xyg-v0.6.0rc01",
        "xyg-v01.6.0",
        "xyg-v0.06.0",
        "xyg-v0.6",
        "xyg-v0.6.0.1",
        "v0.6.0-rc.5",
        "0.6.0-rc.5",
        "xyg-v0.6.0-rc." + chr(0x665),
        "",
    ],
)
def test_malformed_and_unreleasable_tags_fail(tag: str) -> None:
    with pytest.raises(ValueError, match="invalid XYG release tag"):
        rv.parse_tag(tag)


def test_errors_are_actionable() -> None:
    with pytest.raises(ValueError, match="never releasable"):
        rv.parse_tag("xyg-v0.6.0.dev1")
    with pytest.raises(ValueError, match="leading zeros"):
        rv.parse_tag("xyg-v0.6.0-rc.05")
    with pytest.raises(ValueError, match=r"-rc\.N"):
        rv.parse_tag("xyg-v0.6.0-rc5")


@pytest.mark.parametrize("version", ["0.6.0-rc.5", "0.6.0rc5", "0.6.0.dev1", "0.6.0rc05", "1.2"])
def test_python_spelling_rejects_other_ecosystems_forms(version: str) -> None:
    if version == "0.6.0rc5":
        assert rv.parse_python(version).npm == "0.6.0-rc.5"
        return
    with pytest.raises(ValueError, match="invalid XYG Python version"):
        rv.parse_python(version)


@pytest.mark.parametrize("version", ["0.6.0rc5", "0.6.0-rc.05", "0.6.0-rc.5+b", "0.6.0-dryrun.1"])
def test_npm_spelling_rejects_other_forms(version: str) -> None:
    with pytest.raises(ValueError, match="invalid XYG npm version"):
        rv.parse_npm(version)


@pytest.mark.parametrize(
    ("python", "npm", "which"),
    [
        ("0.6.0rc4", "0.6.0-rc.5", "Python"),
        ("0.6.0rc5", "0.6.0-rc.4", "npm"),
        ("0.6.0", "0.6.0-rc.5", "Python"),
        ("0.6.0rc5", "0.6.0", "npm"),
    ],
)
def test_cohort_mismatch_is_named(python: str, npm: str, which: str) -> None:
    with pytest.raises(ValueError, match=f"{which} version .* does not match tag"):
        rv.require_cohort(tag="xyg-v0.6.0-rc.5", python=python, npm=npm)
