"""Lock the #51 Python package identity cutover."""

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


def test_hatch_packages_only_python_xyg() -> None:
    data = _pyproject()
    packages = data["tool"]["hatch"]["build"]["targets"]["wheel"]["packages"]
    assert "python/xyg" in packages
    assert "python/xy" not in packages
    assert (ROOT / "python" / "xyg").is_dir()
    assert not (ROOT / "python" / "xy").exists()


def test_import_xyg_reports_xyg_distribution_version() -> None:
    import xyg

    assert xyg.__name__ == "xyg"
    # Installed editable/dev or wheel: version comes from the xyg distribution.
    assert importlib.metadata.version("xyg") == xyg.__version__


def test_import_xy_is_intentionally_absent_after_cutover() -> None:
    with pytest.raises(ModuleNotFoundError):
        importlib.import_module("xy")


def test_reflex_adapter_namespace_unchanged_for_this_slice() -> None:
    # #51 Non-Goal: retain the established reflex_xy integration namespace.
    assert (ROOT / "python" / "reflex_xy").is_dir()
    import reflex_xy

    assert reflex_xy.__name__ == "reflex_xy"
