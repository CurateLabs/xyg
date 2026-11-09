"""Native viewport proof is required by existing CI commands, once per lane."""

import json
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


def test_node_command_preserves_unique_parent_union_and_requires_live_browser():
    proof = json.loads(
        (
            ROOT / "spec/performance/chunked-native-installed-2026-11-07/parent-node-tests.json"
        ).read_text()
    )
    current = json.loads((ROOT / "packages/xy-node/package.json").read_text())["scripts"][
        "test"
    ].split()
    assert current[:2] == ["node", "--test"]
    tests = current[2:]
    assert len(tests) == len(set(tests))
    # Later qualified integration adds five-view lifecycle coverage; preserve
    # the immutable original producer list and require this addition explicitly.
    assert set(tests) == {"test/geo-five-temporal.test.mjs"}.union(proof["requiredAdded"]).union(
        *(set(p["tests"]) for p in proof["parents"])
    )


def test_floor_installs_parser_required_by_workflow_guard_collection():
    import shlex

    ci = yaml.safe_load((ROOT / ".github/workflows/ci.yml").read_text())
    floor = next(job for job in ci["jobs"].values() if job.get("name") == "Python 3.11 floor")
    install = next(
        step["run"]
        for step in floor["steps"]
        if step.get("name") == "Install package for Python 3.11"
    )
    commands = [
        shlex.split(line)
        for line in install.splitlines()
        if line.strip().startswith("uv pip install ")
    ]
    assert len(commands) == 1
    assert commands[0][:3] == ["uv", "pip", "install"]
    assert "pyyaml>=6" in commands[0]


def test_existing_python_job_requires_installed_render_without_skipping_or_duplicate_gate():
    ci = yaml.safe_load((ROOT / ".github/workflows/ci.yml").read_text())
    run = next(
        s["run"]
        for s in ci["jobs"]["test"]["steps"]
        if s.get("name") == "Python tests (native core)"
    )
    assert "export XY_REQUIRE_BROWSER=1" in run
    assert 'export XYG_TEST_CHROMIUM="$XYG_CHROMIUM"' in run
    required = [
        "tests/test_chunked_live.py",
        "tests/test_chunked_lifecycle.py",
        "tests/test_chunked_installed.py",
    ]
    commands = [
        line.strip() for line in run.splitlines() if line.strip().startswith(".venv/bin/pytest")
    ]
    assert len(commands) == 2
    assert commands[0].split()[2:] == required
    assert commands[1].split()[2:] == ["--ignore=" + name for name in required]
    assert "||" not in run and "continue-on-error" not in run


def test_floor_uses_pinned_browser_for_required_offline_fixtures():
    ci = yaml.safe_load((ROOT / ".github/workflows/ci.yml").read_text())
    floor = ci["jobs"]["python_floor"]
    install = next(
        step
        for step in floor["steps"]
        if step.get("name") == "Install pinned Chromium for Python floor"
    )
    assert install["run"] == "npx playwright install chromium"
    assert "if" not in install and not install.get("continue-on-error")
    run = next(
        step["run"]
        for step in floor["steps"]
        if step.get("name") == "Python 3.11 tests (native core)"
    )
    assert "export XYG_CHROMIUM=" in run
    assert "require('playwright').chromium.executablePath()" in run
    assert run.splitlines()[-1] == ".venv/bin/python -m pytest -q"
    assert "||" not in run and "continue-on-error" not in run


def test_python_native_lanes_export_library_to_node_child_processes():
    ci = yaml.safe_load((ROOT / ".github/workflows/ci.yml").read_text())
    for job, name in [
        ("test", "Python tests (native core)"),
        ("python_floor", "Python 3.11 tests (native core)"),
    ]:
        step = next(s for s in ci["jobs"][job]["steps"] if s.get("name") == name)
        lines = step["run"].splitlines()
        export = 'export XYG_NATIVE_LIB="$GITHUB_WORKSPACE/target/release/libxyg_core.so"'
        assert lines[0] == export
        assert all("XYG_NATIVE_LIB" not in line for line in lines[1:])
        assert "if" not in step and not step.get("continue-on-error")
