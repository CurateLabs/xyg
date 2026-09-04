"""Structural contracts for the release-authoritative CodSpeed harness."""

from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_codspeed_does_not_import_private_module_constants() -> None:
    """Hub moves must not break a benchmark at runtime through stale constants."""
    source = (ROOT / "benchmarks" / "test_codspeed_kernels.py").read_text()
    tree = ast.parse(source)
    references = {
        f"{node.value.id}.{node.attr}"
        for node in ast.walk(tree)
        if isinstance(node, ast.Attribute)
        and isinstance(node.value, ast.Name)
        and node.attr.startswith("_")
        and node.attr[1:].isupper()
    }
    assert references == set()
