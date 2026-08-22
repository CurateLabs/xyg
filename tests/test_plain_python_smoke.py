"""Plain Python host boundary smoke."""

from __future__ import annotations

import sys
import types

from scripts import plain_python_smoke


def test_plain_python_build_and_offline_export_need_no_other_host() -> None:
    assert plain_python_smoke.main(require_installed=False) == 0


def test_plain_python_smoke_ignores_frameworks_loaded_before_its_boundary(monkeypatch) -> None:
    monkeypatch.setitem(sys.modules, "reflex", types.ModuleType("reflex"))
    monkeypatch.setitem(sys.modules, "anywidget", types.ModuleType("anywidget"))
    assert plain_python_smoke.main(require_installed=False) == 0
