"""Known unresolved scheduled/main failures block release readiness (#1008)."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from scripts import check_scheduled_evidence as gate

NOW = datetime(2026, 10, 19, 15, 0, tzinfo=UTC)


DETECTOR = {"name": "Check for changed main", "conclusion": "success"}


def _evidence(conclusion: str) -> list[dict]:
    """A run that executed its evidence job and the detector that allowed it."""
    return [DETECTOR, {"name": "Run benchmarks", "conclusion": conclusion}]


def _run(
    conclusion: str,
    created: str,
    *,
    status: str = "completed",
    sha: str = "4e27ef4b0e1a",
    jobs: list[dict] | None = None,
) -> dict:
    return {
        "jobs": jobs if jobs is not None else _evidence(conclusion),
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
CI_RUN = {
    "databaseId": 9,
    "event": "push",
    "status": "completed",
    "conclusion": "success",
    "headSha": "4e27ef4b0e1a",
    "createdAt": "2026-10-19T12:00:00Z",
    "url": "https://github.com/CurateLabs/xyg/actions/runs/9",
}


def test_green_scheduled_runs_and_main_ci_do_not_block() -> None:
    assert (
        gate.evaluate(scheduled=_scheduled(), ci_runs=[CI_RUN], ci_jobs=GREEN_JOBS, now=NOW) == []
    )


def test_repeatedly_failing_scheduled_run_blocks_readiness() -> None:
    """The #1008 state: CodSpeed failed daily at the current main head."""
    scheduled = {
        "codspeed.yml": [_run("failure", f"2026-10-1{day}T12:00:00Z") for day in (5, 6, 7, 8, 9)],
        "density-100m.yml": [_run("success", "2026-10-19T06:31:00Z")],
    }

    findings = gate.evaluate(scheduled=scheduled, ci_runs=[CI_RUN], ci_jobs=GREEN_JOBS, now=NOW)

    assert len(findings) == 1
    assert "codspeed.yml: the newest evidence execution concluded 'failure'" in findings[0]
    assert "linked open issue" in findings[0]


SKIPPED_BY_DETECTOR = [
    DETECTOR,
    {"name": "Run benchmarks", "conclusion": "skipped"},
    {"name": "Main-only browser evidence (not CodSpeed)", "conclusion": "skipped"},
]


def test_detector_skipped_success_does_not_clear_a_failed_rerun() -> None:
    """CodSpeed succeeds on S, a manual rerun on S fails, then the schedule skips.

    The next scheduled run concludes ``success`` because the detector saw the earlier green
    run on S and skipped every evidence job; no benchmark execution succeeded after the
    failed rerun, so readiness must stay blocked.
    """
    scheduled = {
        "codspeed.yml": [
            _run("success", "2026-10-17T12:00:00Z"),
            _run("failure", "2026-10-18T09:00:00Z"),
            _run("success", "2026-10-19T12:00:00Z", jobs=SKIPPED_BY_DETECTOR),
        ],
        "density-100m.yml": [_run("success", "2026-10-19T06:31:00Z")],
    }

    findings = gate.evaluate(scheduled=scheduled, ci_runs=[CI_RUN], ci_jobs=GREEN_JOBS, now=NOW)

    assert len(findings) == 1
    assert "codspeed.yml: the newest evidence execution concluded 'failure'" in findings[0]
    assert "2026-10-18T09:00:00Z" in findings[0]
    assert "detector-skipped runs do not count" in findings[0]


def test_detector_skip_after_a_green_execution_is_still_green() -> None:
    scheduled = {
        "codspeed.yml": [
            _run("success", "2026-10-18T12:00:00Z"),
            _run("success", "2026-10-19T12:00:00Z", jobs=SKIPPED_BY_DETECTOR),
        ],
        "density-100m.yml": [_run("success", "2026-10-19T06:31:00Z")],
    }

    assert gate.evaluate(scheduled=scheduled, ci_runs=[CI_RUN], ci_jobs=GREEN_JOBS, now=NOW) == []


def test_only_skipped_runs_are_absent_evidence_and_a_failed_detector_is_a_failure() -> None:
    skipped = {
        "codspeed.yml": [_run("success", "2026-10-19T12:00:00Z", jobs=SKIPPED_BY_DETECTOR)],
        "density-100m.yml": [_run("success", "2026-10-19T06:31:00Z")],
    }
    findings = gate.evaluate(scheduled=skipped, ci_runs=[CI_RUN], ci_jobs=GREEN_JOBS, now=NOW)
    assert len(findings) == 1 and "no run on main executed its evidence jobs" in findings[0]

    broken_detector = {
        "codspeed.yml": [
            _run(
                "failure",
                "2026-10-19T12:00:00Z",
                jobs=[{"name": "Check for changed main", "conclusion": "failure"}]
                + SKIPPED_BY_DETECTOR[1:],
            )
        ],
        "density-100m.yml": [_run("success", "2026-10-19T06:31:00Z")],
    }
    findings = gate.evaluate(
        scheduled=broken_detector, ci_runs=[CI_RUN], ci_jobs=GREEN_JOBS, now=NOW
    )
    assert len(findings) == 1 and "newest evidence execution concluded 'failure'" in findings[0]


def test_partially_skipped_evidence_is_not_green() -> None:
    mixed = [
        DETECTOR,
        {"name": "Run benchmarks", "conclusion": "success"},
        {"name": "Main-only browser evidence (not CodSpeed)", "conclusion": "skipped"},
    ]
    scheduled = {
        "codspeed.yml": [_run("success", "2026-10-19T12:00:00Z", jobs=mixed)],
        "density-100m.yml": [_run("success", "2026-10-19T06:31:00Z")],
    }
    findings = gate.evaluate(scheduled=scheduled, ci_runs=[CI_RUN], ci_jobs=GREEN_JOBS, now=NOW)
    assert len(findings) == 1


def test_a_later_green_run_clears_the_block() -> None:
    scheduled = _scheduled()
    scheduled["codspeed.yml"].insert(0, _run("failure", "2026-10-15T12:00:00Z"))

    assert gate.evaluate(scheduled=scheduled, ci_runs=[CI_RUN], ci_jobs=GREEN_JOBS, now=NOW) == []


def test_missing_cancelled_in_progress_and_stale_evidence_block() -> None:
    cancelled_only = {
        "codspeed.yml": [_run("cancelled", "2026-10-19T12:00:00Z")],
        "density-100m.yml": [_run("", "2026-10-19T12:00:00Z", status="in_progress")],
    }
    findings = gate.evaluate(
        scheduled=cancelled_only, ci_runs=[CI_RUN], ci_jobs=GREEN_JOBS, now=NOW
    )
    assert len(findings) == 2 and all("no completed run" in f for f in findings)

    stale = {name: [_run("success", "2026-10-01T00:00:00Z")] for name in gate.SCHEDULED_WORKFLOWS}
    findings = gate.evaluate(scheduled=stale, ci_runs=[CI_RUN], ci_jobs=GREEN_JOBS, now=NOW)
    assert len(findings) == 2 and all("stale" in f for f in findings)


def test_failed_main_ci_jobs_block_even_when_the_aggregate_is_green() -> None:
    jobs = [
        {"name": "Release surfaces", "conclusion": "success"},
        {"name": "Matplotlib 3.11 reference compatibility", "conclusion": "failure"},
        {"name": "Merge and verify benchmark reports", "conclusion": "timed_out"},
    ]

    findings = gate.evaluate(
        scheduled=_scheduled(), ci_runs=[{**CI_RUN, "url": "run-url"}], ci_jobs=jobs, now=NOW
    )

    assert len(findings) == 2
    assert "Matplotlib 3.11 reference compatibility" in findings[0]
    assert gate.evaluate(scheduled=_scheduled(), ci_runs=[], ci_jobs=[], now=NOW) == [
        "ci.yml: no completed push run on main to inspect"
    ]


def test_cli_replays_fixture_and_exits_nonzero_when_blocked(tmp_path: Path, capsys) -> None:
    fixture = tmp_path / "evidence.json"
    fixture.write_text(
        json.dumps(
            {
                "scheduled": _scheduled(**{"codspeed.yml": "failure"}),
                "ci_runs": [CI_RUN],
                "ci_jobs": GREEN_JOBS,
            }
        ),
        encoding="utf-8",
    )

    assert gate.main(["--fixture", str(fixture), "--now", "2026-10-19T15:00:00Z"]) == 1
    assert "BLOCKED" in capsys.readouterr().err

    fixture.write_text(
        json.dumps({"scheduled": _scheduled(), "ci_runs": [CI_RUN], "ci_jobs": GREEN_JOBS}),
        encoding="utf-8",
    )
    assert gate.main(["--fixture", str(fixture), "--now", "2026-10-19T15:00:00Z"]) == 0
    assert gate.main(["--fixture", str(tmp_path / "absent.json")]) == 2


def test_latest_completed_push_run_is_selected_not_the_newest_in_progress_one() -> None:
    older = {**CI_RUN, "databaseId": 1, "createdAt": "2026-10-18T12:00:00Z"}
    newest_in_progress = {
        **CI_RUN,
        "databaseId": 3,
        "status": "in_progress",
        "conclusion": "",
        "createdAt": "2026-10-19T14:00:00Z",
    }
    assert gate.select_ci_run([older, CI_RUN, newest_in_progress]) == CI_RUN
    assert gate.select_ci_run([newest_in_progress]) is None


def test_in_progress_main_run_is_no_evidence_yet_not_green() -> None:
    pending = {
        **CI_RUN,
        "status": "in_progress",
        "conclusion": "",
        "createdAt": "2026-10-19T14:00:00Z",
    }

    findings = gate.evaluate(
        scheduled=_scheduled(), ci_runs=[pending, CI_RUN], ci_jobs=GREEN_JOBS, now=NOW
    )
    assert len(findings) == 1 and "'in_progress': no evidence yet" in findings[0]

    only_pending = gate.evaluate(scheduled=_scheduled(), ci_runs=[pending], ci_jobs=[], now=NOW)
    assert any("no evidence yet" in f for f in only_pending)
    assert any("no completed push run" in f for f in only_pending)


def test_run_level_conclusion_must_be_success_even_with_green_jobs() -> None:
    failed = {**CI_RUN, "conclusion": "failure"}
    findings = gate.evaluate(scheduled=_scheduled(), ci_runs=[failed], ci_jobs=GREEN_JOBS, now=NOW)
    assert len(findings) == 1 and "concluded 'failure'" in findings[0]
    cancelled = {**CI_RUN, "conclusion": "cancelled"}
    assert gate.evaluate(scheduled=_scheduled(), ci_runs=[cancelled], ci_jobs=GREEN_JOBS, now=NOW)


def test_zero_job_startup_failure_blocks() -> None:
    startup = {**CI_RUN, "conclusion": "failure"}
    findings = gate.evaluate(scheduled=_scheduled(), ci_runs=[startup], ci_jobs=[], now=NOW)
    assert any("no jobs (startup failure)" in f for f in findings)
    # Even a "successful" run with zero jobs is no evidence.
    findings = gate.evaluate(scheduled=_scheduled(), ci_runs=[CI_RUN], ci_jobs=[], now=NOW)
    assert findings and "no jobs (startup failure)" in findings[0]
