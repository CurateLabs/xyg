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
    assert set(tests) == set(proof["requiredAdded"]).union(
        *(set(p["tests"]) for p in proof["parents"])
    )


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
