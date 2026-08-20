"""Lock the pre-#51 Python package identity split.

Distribution is already ``xyg``; the import namespace remains ``xy`` until the
mechanical ``python/xy`` → ``python/xyg`` cutover. This suite prevents silent
regression of either side of that split.
"""

from __future__ import annotations

import importlib
import importlib.metadata
import re
import tomllib
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PYPROJECT = ROOT / "pyproject.toml"


def _pyproject() -> dict:
    return tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))


def test_distribution_name_is_xyg_not_xy() -> None:
    data = _pyproject()
    assert data["project"]["name"] == "xyg"
    # Guard against a silent rename of the hatch wheel packages back to a
    # published ``xy`` project identity.
    text = PYPROJECT.read_text(encoding="utf-8")
    assert re.search(r'(?m)^name\s*=\s*"xy"\s*$', text) is None


def test_hatch_still_packages_python_xy_until_cutover() -> None:
    data = _pyproject()
    packages = data["tool"]["hatch"]["build"]["targets"]["wheel"]["packages"]
    assert "python/xy" in packages
    assert "python/xyg" not in packages
    assert (ROOT / "python" / "xy").is_dir()
    assert not (ROOT / "python" / "xyg").exists()


def test_import_xy_works_and_reports_xyg_distribution_version() -> None:
    import xy

    assert xy.__name__ == "xy"
    # Installed editable/dev or wheel: version comes from the xyg distribution.
    assert importlib.metadata.version("xyg") == xy.__version__


def test_import_xyg_absent_until_cutover() -> None:
    with pytest.raises(ModuleNotFoundError):
        importlib.import_module("xyg")


def test_reflex_adapter_namespace_unchanged_for_this_slice() -> None:
    # #51 Non-Goal: retain reflex_xy (matrix reflex_xyg is a later branding slice).
    assert (ROOT / "python" / "reflex_xy").is_dir()
    import reflex_xy

    assert reflex_xy.__name__ == "reflex_xy"
