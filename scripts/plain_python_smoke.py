#!/usr/bin/env python3
"""Prove an installed XYG Python host needs no Node, browser, or Reflex runtime."""

from __future__ import annotations

import subprocess
import sys
from importlib import resources
from pathlib import Path
from typing import NoReturn

FORBIDDEN_MODULE_PREFIXES = ("reflex", "reflex_xy")


def _reject_process(*args: object, **kwargs: object) -> NoReturn:
    del args, kwargs
    raise AssertionError("plain XYG Python unexpectedly launched an external process")


def _new_optional_modules(before: set[str]) -> list[str]:
    return sorted(
        name
        for name in sys.modules.keys() - before
        if name == "anywidget"
        or any(
            name == prefix or name.startswith(f"{prefix}.") for prefix in FORBIDDEN_MODULE_PREFIXES
        )
    )


def main(*, require_installed: bool = True) -> int:
    modules_before = set(sys.modules)
    original_popen = subprocess.Popen
    subprocess.Popen = _reject_process  # type: ignore[assignment]
    try:
        import xyg

        module_path = Path(xyg.__file__).resolve()
        if require_installed and not module_path.is_relative_to(Path(sys.prefix).resolve()):
            raise AssertionError(
                f"plain XYG smoke imported {module_path} outside isolated environment {sys.prefix}"
            )
        eager = _new_optional_modules(modules_before)
        if eager:
            raise AssertionError(f"plain import loaded optional host frameworks: {eager}")
        chart = xyg.scatter_chart(xyg.scatter(x=[0.0, 1.0], y=[1.0, 0.0]))
        html = chart.to_html()
        if not html.startswith("<!doctype html>") or "connect-src 'none'" not in html:
            raise AssertionError("plain XYG Python did not produce self-contained offline HTML")
        static = resources.files("xyg") / "static"
        for name in ("index.js", "standalone.js"):
            if not (static / name).is_file():
                raise AssertionError(f"installed xyg is missing bundled offline asset {name}")
        leaked = _new_optional_modules(modules_before)
        if leaked:
            raise AssertionError(f"plain chart/export loaded Reflex: {leaked}")
    finally:
        subprocess.Popen = original_popen
    print("plain XYG Python host OK: native Rust + bundled offline client; no Node/browser/Reflex")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
