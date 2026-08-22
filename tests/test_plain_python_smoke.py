"""Plain Python host boundary smoke."""

from __future__ import annotations

import sys
import types
from importlib import metadata

import pytest
from scripts import plain_python_smoke


def test_plain_python_build_and_offline_export_need_no_other_host() -> None:
    assert plain_python_smoke.main(require_installed=False) == 0


def test_plain_python_smoke_ignores_frameworks_loaded_before_its_boundary(monkeypatch) -> None:
    monkeypatch.setitem(sys.modules, "reflex", types.ModuleType("reflex"))
    monkeypatch.setitem(sys.modules, "anywidget", types.ModuleType("anywidget"))
    assert plain_python_smoke.main(require_installed=False) == 0


def test_plain_python_smoke_accepts_environment_without_reflex(monkeypatch) -> None:
    def missing(_name: str) -> metadata.Distribution:
        raise metadata.PackageNotFoundError

    monkeypatch.setattr(plain_python_smoke.metadata, "distribution", missing)
    plain_python_smoke._assert_reflex_not_installed()


def test_plain_python_smoke_rejects_installed_reflex(monkeypatch) -> None:
    distribution = types.SimpleNamespace(version="0.9.6")
    monkeypatch.setattr(plain_python_smoke.metadata, "distribution", lambda _name: distribution)

    with pytest.raises(AssertionError, match=r"optional Reflex distribution 0\.9\.6"):
        plain_python_smoke._assert_reflex_not_installed()
