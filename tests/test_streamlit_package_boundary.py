"""Framework guardrails run even when the optional Streamlit tests skip.

The installed-consumer gate also runs this against the actual wheel package.
"""

from __future__ import annotations

import ast
from importlib.metadata import distribution
from pathlib import Path

import xyg


def test_streamlit_is_not_a_package_dependency_or_extra() -> None:
    metadata = distribution("xyg").metadata
    assert not any(
        "streamlit" in requirement.lower() for requirement in metadata.get_all("Requires-Dist", [])
    )
    assert not any("streamlit" in extra.lower() for extra in metadata.get_all("Provides-Extra", []))


def test_streamlit_has_no_package_import_or_adapter_namespace() -> None:
    package = Path(xyg.__file__).parent
    for path in package.rglob("*"):
        assert "streamlit" not in path.name.lower(), str(path)
        if path.suffix != ".py":
            continue
        for node in ast.walk(ast.parse(path.read_text(), filename=str(path))):
            imports = []
            if isinstance(node, ast.Import):
                imports = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                imports = [node.module]
            assert not any(name.split(".")[0] == "streamlit" for name in imports), str(path)
