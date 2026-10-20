"""Release-surface classifier and non-skippable aggregate contracts."""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

import pytest
from scripts.classify_release_surface import classify
from scripts.verify_release_surface_results import (
    ALWAYS_HARD_JOBS,
    HARD_JOBS,
    MAIN_EVIDENCE_JOBS,
    RELEASE_SURFACE_JOBS,
    applicable_jobs,
    verify,
)

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "verify_release_surface_results.py"
WORKFLOW = Path(__file__).resolve().parents[1] / ".github" / "workflows" / "ci.yml"
SCENARIOS = (
    ("pull_request", False),
    ("pull_request", True),
    ("merge_group", True),
    ("push", True),
    ("workflow_dispatch", True),
)


def _green(*, event: str, required: bool) -> dict[str, str]:
    applicable = applicable_jobs(event=event, required=required)
    return {name: ("success" if name in applicable else "skipped") for name in HARD_JOBS}


REQUIRED_RESULTS = _green(event="merge_group", required=True)


def test_release_classifier_covers_every_contract_family() -> None:
    for path in (
        ".codspeed/config.json",
        "benchmarks/test_codspeed_kernels.py",
        "crates/xyg-core/src/lib.rs",
        "spec/abi/xyg.h",
        "spec/wasm/abi.json",
        "python/xyg/_figure.py",
        "python/xyg/_figure_export.py",
        "python/xyg/_payload.py",
        "python/xyg/_scene_v3.py",
        "packages/xy-node/src/figure.js",
        "js/src/49_wasm_density.ts",
        "hatch_build.py",
        "Makefile",
        "package.json",
        "pyproject.toml",
        ".github/workflows/ci.yml",
        ".github/dependabot.yml",
    ):
        assert classify([path]), path


def test_release_classifier_leaves_prose_only_change_optional() -> None:
    assert not classify(["docs/guide.md", "spec/design/example.md"])
    assert not classify(
        ["README.md", "CHANGELOG.md", "LICENSE", "spec/performance/run/summary.json"]
    )


@pytest.mark.parametrize(
    "path",
    [
        "tsconfig.json",  # a root file nobody listed
        "vite.config.ts",
        "examples/chart.py",
        "demo/js_demo.mjs",
        ".gitignore",
        "new_top_level_dir/anything.txt",
        "python/README.md",  # prose suffix inside a release prefix is still code-adjacent
        "spec/abi/xyg.h",  # generated-contract inputs are not prose
        "spec/wasm/abi.json",
    ],
)
def test_release_classifier_treats_unknown_paths_as_release_surface(path: str) -> None:
    assert classify([path]), path


def test_release_classifier_mixed_change_is_required() -> None:
    assert classify(["docs/guide.md", "spec/design/example.md", "tsconfig.json"])


def test_inventory_covers_the_failed_main_jobs_of_1008() -> None:
    """Run 38640943006: these three failed while Release surfaces passed."""
    for name in ("matplotlib_reference", "benchmark_methodology", "benchmark"):
        assert name in HARD_JOBS


def test_required_aggregate_rejects_skipped_release_job() -> None:
    results = {**REQUIRED_RESULTS, "wheels": "skipped"}
    assert verify(required=True, results=results, event="merge_group") == [
        "release-surface job wheels must succeed, got 'skipped'"
    ]


def test_required_aggregate_accepts_complete_matrix() -> None:
    assert verify(required=True, results=REQUIRED_RESULTS, event="merge_group") == []


def test_nonrelease_aggregate_accepts_expected_skips_but_not_failures() -> None:
    """Applicability branch: a prose-only PR records inapplicable jobs as skipped."""
    results = _green(event="pull_request", required=False)
    assert {n for n, r in results.items() if r == "skipped"} == {
        *RELEASE_SURFACE_JOBS,
        *MAIN_EVIDENCE_JOBS,
    }
    assert verify(required=False, results=results, event="pull_request") == []
    results["sdist"] = "failure"
    assert verify(required=False, results=results, event="pull_request") == [
        "optional release-surface job sdist failed with 'failure'"
    ]


@pytest.mark.parametrize(("event", "required"), SCENARIOS)
def test_every_scenario_accepts_exactly_its_applicable_jobs(event: str, required: bool) -> None:
    assert (
        verify(required=required, results=_green(event=event, required=required), event=event) == []
    )


@pytest.mark.parametrize(("event", "required"), SCENARIOS)
@pytest.mark.parametrize("injected", ["failure", "cancelled", "skipped", "missing"])
def test_injected_failure_in_each_applicable_job_fails_the_aggregate(
    event: str, required: bool, injected: str
) -> None:
    """BDD: an applicable hard failure (or silent skip) blocks the merge queue."""
    green = _green(event=event, required=required)
    for name in sorted(applicable_jobs(event=event, required=required)):
        results = (
            {k: v for k, v in green.items() if k != name}
            if injected == "missing"
            else {**green, name: injected}
        )
        assert verify(required=required, results=results, event=event), (event, name, injected)


@pytest.mark.parametrize(("event", "required"), SCENARIOS)
def test_inapplicable_jobs_may_skip_but_never_fail(event: str, required: bool) -> None:
    green = _green(event=event, required=required)
    inapplicable = set(HARD_JOBS) - applicable_jobs(event=event, required=required)
    for name in sorted(inapplicable):
        assert verify(required=required, results={**green, name: "skipped"}, event=event) == []
        for bad in ("failure", "cancelled"):
            assert verify(required=required, results={**green, name: bad}, event=event), (name, bad)


def test_main_evidence_is_applicable_only_after_merge() -> None:
    for event in ("push", "workflow_dispatch"):
        assert set(MAIN_EVIDENCE_JOBS) <= applicable_jobs(event=event, required=True)
    for event in ("pull_request", "merge_group"):
        assert not set(MAIN_EVIDENCE_JOBS) & applicable_jobs(event=event, required=True)
    results = {**_green(event="push", required=True), "benchmark": "skipped"}
    assert verify(required=True, results=results, event="push") == [
        "main evidence job benchmark must succeed on push, got 'skipped'"
    ]


def test_baseline_jobs_are_hard_in_every_scenario() -> None:
    for event, required in SCENARIOS:
        for name in ALWAYS_HARD_JOBS:
            assert name in applicable_jobs(event=event, required=required)


def test_unclassified_job_cannot_be_passed_to_the_aggregate() -> None:
    results = {**REQUIRED_RESULTS, "mystery": "success"}
    assert verify(required=True, results=results, event="merge_group") == [
        "unclassified job 'mystery' passed to the Release surfaces aggregate"
    ]


def _workflow_command(event: str, required: bool, overrides: dict[str, str]) -> list[str]:
    """Rebuild the aggregate's real argv from ci.yml, substituting injected job results."""
    text = WORKFLOW.read_text(encoding="utf-8")
    start = text.index("python3 scripts/verify_release_surface_results.py")
    command = text[start : text.index("\n\n", start)].replace("\\\n", " ")
    applicable = applicable_jobs(event=event, required=required)

    def result(match: re.Match[str]) -> str:
        name = match.group(1)
        if name in overrides:
            return overrides[name]
        return "success" if name in applicable else "skipped"

    command = re.sub(r"\$\{\{ needs\.([a-z_0-9]+)\.result \}\}", result, command)
    command = command.replace(
        "${{ needs.release_surface_changes.outputs.required }}", str(required).lower()
    )
    command = command.replace("${{ github.event_name }}", event)
    argv = [piece.strip('"') for piece in command.split()]
    return [sys.executable, "-I", str(SCRIPT), *argv[2:]]


@pytest.mark.parametrize(("event", "required"), SCENARIOS)
def test_workflow_aggregate_command_propagates_each_injected_failure(
    event: str, required: bool
) -> None:
    """Self-test through the real ci.yml command line, including a merge_group event."""
    accepted = subprocess.run(
        _workflow_command(event, required, {}), capture_output=True, text=True, check=False
    )
    assert accepted.returncode == 0, accepted.stdout
    assert f"for {event}" in accepted.stdout
    for name in sorted(applicable_jobs(event=event, required=required)):
        rejected = subprocess.run(
            _workflow_command(event, required, {name: "failure"}),
            capture_output=True,
            text=True,
            check=False,
        )
        assert rejected.returncode == 1, (event, name)
        assert name in rejected.stdout


METHODOLOGY_STEP = "Benchmark methodology contract (smallest sizes, report verified)"


def _methodology_commands(root: Path) -> list[list[str]]:
    """The real `test`-job step commands, runnable against ``root`` as RUNNER_TEMP."""
    import shlex

    import yaml

    workflow = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    step = next(s for s in workflow["jobs"]["test"]["steps"] if s.get("name") == METHODOLOGY_STEP)
    commands = []
    for line in step["run"].splitlines():
        argv = shlex.split(line.replace("$RUNNER_TEMP", str(root)))
        if argv[0] == ".venv/bin/python":
            argv[0] = sys.executable
        commands.append(argv)
    return commands


def _run_methodology_step(root: Path, *, tamper: bool) -> str:
    """Run the step as the runner would (set -e) and return the `test` job conclusion."""
    for argv in _methodology_commands(root):
        if (
            tamper
            and argv[1].endswith("verify_benchmark_report.py")
            and "workflows.json" in argv[2]
        ):
            report = Path(argv[2])
            report.write_text(
                report.read_text(encoding="utf-8").replace(
                    '"oracle_status": "pass"', '"oracle_status": "FAIL"'
                ),
                encoding="utf-8",
            )
        if subprocess.run(argv, capture_output=True, text=True, check=False).returncode != 0:
            return "failure"
    return "success"


@pytest.mark.parametrize("event", ["merge_group", "pull_request"])
def test_broken_benchmark_report_fails_the_aggregate_before_merge(
    event: str, tmp_path: Path
) -> None:
    """#1005/#1008: the methodology producers and report verifier gate merge_group and PRs.

    The step lives in the always-hard ``test`` job, so a broken report turns ``test`` red
    and the aggregate rejects it on the pre-merge events, not only after the push.
    """
    assert _run_methodology_step(tmp_path / "ok", tamper=False) == "success"
    assert _run_methodology_step(tmp_path / "broken", tamper=True) == "failure"

    green = _green(event=event, required=True)
    assert verify(required=True, results=green, event=event) == []
    red = {**green, "test": "failure"}
    assert verify(required=True, results=red, event=event) == ["test must succeed, got 'failure'"]
