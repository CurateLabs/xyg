"""Plain Python host boundary smoke."""

from __future__ import annotations

from scripts import plain_python_smoke


def test_plain_python_build_and_offline_export_need_no_other_host() -> None:
    assert plain_python_smoke.main(require_installed=False) == 0
