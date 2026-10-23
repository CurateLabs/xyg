from __future__ import annotations

import ast
import re
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CORE_PACKAGE = ROOT / "python" / "xyg"


def _dependency_name(requirement: str) -> str:
    requirement = requirement.split(";", 1)[0].strip()
    match = re.match(r"([A-Za-z0-9_.-]+)", requirement)
    assert match is not None, requirement
    return match.group(1).replace("_", "-").lower()


def test_core_runtime_dependencies_do_not_include_reflex() -> None:
    data = tomllib.loads(ROOT.joinpath("pyproject.toml").read_text(encoding="utf-8"))
    dependencies = (data.get("project") or {}).get("dependencies") or []

    runtime_names = {_dependency_name(requirement) for requirement in dependencies}

    assert runtime_names == {"numpy", "anywidget"}


def test_consumer_frameworks_are_dev_only() -> None:
    data = tomllib.loads(ROOT.joinpath("pyproject.toml").read_text(encoding="utf-8"))
    project = data["project"]
    groups = data["dependency-groups"]
    assert not project.get("optional-dependencies")
    assert {"dev", "codspeed"} <= groups.keys()
    requirements = [
        requirement
        for values in groups.values()
        for requirement in values
        if isinstance(requirement, str)
    ]
    names = {_dependency_name(requirement) for requirement in requirements}
    assert not any(name == "reflex" or name.startswith("reflex-") for name in names)
    assert "streamlit>=1.56,<2" in groups["dev"]
    assert "plotly" not in names


def test_core_package_does_not_import_consumer_frameworks() -> None:
    forbidden = ("reflex", "reflex_core", "reflex_base", "streamlit")
    violations: list[str] = []
    for path in sorted(CORE_PACKAGE.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    root = alias.name.split(".", 1)[0]
                    if root in forbidden or root.startswith("reflex_"):
                        violations.append(f"{path.relative_to(ROOT)} imports {alias.name}")
            elif isinstance(node, ast.ImportFrom) and node.module:
                root = node.module.split(".", 1)[0]
                if root in forbidden or root.startswith("reflex_"):
                    violations.append(f"{path.relative_to(ROOT)} imports from {node.module}")

    assert violations == [], f"python/xyg must stay framework-free: {violations}"
