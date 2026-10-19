"""Known unresolved scheduled/main failures block release readiness (#1008)."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from scripts import check_scheduled_evidence as gate

NOW = datetime(2026, 10, 19, 15, 0, tzinfo=UTC)


def _run(
    conclusion: str, created: str, *, status: str = "completed", sha: str = "4e27ef4b0e1a"
) -> dict:
    return {
        "databaseId": 1,
        "event": "schedule",
        "status": status,
        "conclusion": conclusion,
        "headSha": sha,
        "createdAt": created,
        "url": f"https://github.com/CurateLabs/xyg/actions/runs/{created}",
    }


def _scheduled(**latest: str) -> dict[str, list[dict]]:
    return {
        workflow: [
            _run(latest.get(workflow, "success"), "2026-10-19T14:39:46Z"),
            _run("success", "2026-10-18T12:00:00Z"),
        ]
        for workflow in gate.SCHEDULED_WORKFLOWS
    }


GREEN_JOBS = [{"name": "Release surfaces", "conclusion": "success"}]


def test_green_scheduled_runs_and_main_ci_do_not_block() -> None:
    assert (
        gate.evaluate(scheduled=_scheduled(), ci_run={"url": "u"}, ci_jobs=GREEN_JOBS, now=NOW)
        == []
    )


def test_repeatedly_failing_scheduled_run_blocks_readiness() -> None:
    """The #1008 state: CodSpeed failed daily at the current main head."""
    scheduled = {
        "codspeed.yml": [_run("failure", f"2026-10-1{day}T12:00:00Z") for day in (5, 6, 7, 8, 9)],
        "density-100m.yml": [_run("success", "2026-10-19T06:31:00Z")],
    }

    findings = gate.evaluate(scheduled=scheduled, ci_run={"url": "u"}, ci_jobs=GREEN_JOBS, now=NOW)

    assert len(findings) == 1
    assert "codspeed.yml: latest run concluded 'failure'" in findings[0]
    assert "linked open issue" in findings[0]


def test_a_later_green_run_clears_the_block() -> None:
    scheduled = _scheduled()
    scheduled["codspeed.yml"].insert(0, _run("failure", "2026-10-15T12:00:00Z"))

    assert (
        gate.evaluate(scheduled=scheduled, ci_run={"url": "u"}, ci_jobs=GREEN_JOBS, now=NOW) == []
    )


def test_missing_cancelled_in_progress_and_stale_evidence_block() -> None:
    cancelled_only = {
        "codspeed.yml": [_run("cancelled", "2026-10-19T12:00:00Z")],
        "density-100m.yml": [_run("", "2026-10-19T12:00:00Z", status="in_progress")],
    }
    findings = gate.evaluate(
        scheduled=cancelled_only, ci_run={"url": "u"}, ci_jobs=GREEN_JOBS, now=NOW
    )
    assert len(findings) == 2 and all("no completed run" in f for f in findings)

    stale = {name: [_run("success", "2026-10-01T00:00:00Z")] for name in gate.SCHEDULED_WORKFLOWS}
    findings = gate.evaluate(scheduled=stale, ci_run={"url": "u"}, ci_jobs=GREEN_JOBS, now=NOW)
    assert len(findings) == 2 and all("stale" in f for f in findings)


def test_failed_main_ci_jobs_block_even_when_the_aggregate_is_green() -> None:
    jobs = [
        {"name": "Release surfaces", "conclusion": "success"},
        {"name": "Matplotlib 3.11 reference compatibility", "conclusion": "failure"},
        {"name": "Merge and verify benchmark reports", "conclusion": "timed_out"},
    ]

    findings = gate.evaluate(
        scheduled=_scheduled(), ci_run={"url": "run-url"}, ci_jobs=jobs, now=NOW
    )

    assert len(findings) == 2
    assert "Matplotlib 3.11 reference compatibility" in findings[0]
    assert gate.evaluate(scheduled=_scheduled(), ci_run=None, ci_jobs=[], now=NOW) == [
        "ci.yml: no push run on main to inspect"
    ]


def test_cli_replays_fixture_and_exits_nonzero_when_blocked(tmp_path: Path, capsys) -> None:
    fixture = tmp_path / "evidence.json"
    fixture.write_text(
        json.dumps(
            {
                "scheduled": _scheduled(**{"codspeed.yml": "failure"}),
                "ci_run": {"url": "u"},
                "ci_jobs": GREEN_JOBS,
            }
        ),
        encoding="utf-8",
    )

    assert gate.main(["--fixture", str(fixture), "--now", "2026-10-19T15:00:00Z"]) == 1
    assert "BLOCKED" in capsys.readouterr().err

    fixture.write_text(
        json.dumps({"scheduled": _scheduled(), "ci_run": {"url": "u"}, "ci_jobs": GREEN_JOBS}),
        encoding="utf-8",
    )
    assert gate.main(["--fixture", str(fixture), "--now", "2026-10-19T15:00:00Z"]) == 0
    assert gate.main(["--fixture", str(tmp_path / "absent.json")]) == 2
