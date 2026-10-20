#!/usr/bin/env python3
"""Block release readiness on unresolved scheduled-evidence or main-CI failures (#1008).

Scheduled performance and browser evidence (CodSpeed, the density authority) stays
scheduled: it never runs on pull requests and is not a ``Release surfaces`` input. That
must not let a known, repeatedly failing run look like readiness. A release tracker, a
release authorization, or a "main is green" claim runs this check first:

* the newest scheduled run of each workflow on ``main`` that actually executed its
  evidence jobs must have had every one of them succeed, and the scheduler must have
  fired recently. Judgement uses the evidence jobs' own results: a run whose detector
  skipped them (``codspeed_should_run.py`` found an earlier success for the same SHA)
  is not evidence, so it can neither clear nor replace an earlier failed execution. A
  failure blocks until a later *execution* succeeds, and each blocking finding must be
  tracked by an open linked issue (close it only after that later green run);
* the latest completed push CI run on ``main`` must have concluded ``success`` with at
  least one job and no failed, cancelled, or timed-out job; runs still in progress are
  "no evidence yet", never green.

Stdlib only; ``gh`` (read-only ``run list`` / ``run view``) supplies live data, and
``--fixture`` replays recorded JSON so the policy is testable offline.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Optional

SCHEDULED_WORKFLOWS = ("codspeed.yml", "density-100m.yml")
BAD_JOB_CONCLUSIONS = frozenset({"failure", "cancelled", "timed_out", "action_required"})
# Jobs that only decide whether the evidence jobs run; they are not evidence themselves.
DETECTOR_JOBS = frozenset({"Check for changed main"})
RUN_FIELDS = "databaseId,event,status,conclusion,headSha,createdAt,url"


def _parse_time(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def select_ci_run(ci_runs: list[dict[str, Any]]) -> Optional[dict[str, Any]]:
    """The latest COMPLETED push run; queued/in-progress runs are not evidence."""
    completed = [run for run in ci_runs if run.get("status") == "completed"]
    return max(completed, key=lambda run: _parse_time(run["createdAt"])) if completed else None


def evidence_state(run: dict[str, Any]) -> str:
    """``success``, ``failure`` or ``skipped`` from the run's own evidence-job results.

    ``skipped`` means no evidence job executed (the detector declined to run them), which
    is neither green nor red. A run that did not conclude ``success`` without any executed
    evidence job (detector or startup failure) is a failure, never a skip.
    """
    jobs = [job for job in run.get("jobs") or [] if job.get("name") not in DETECTOR_JOBS]
    conclusions = [job.get("conclusion") for job in jobs]
    if jobs and all(conclusion == "skipped" for conclusion in conclusions):
        return "skipped" if run.get("conclusion") == "success" else "failure"
    if jobs and all(conclusion == "success" for conclusion in conclusions):
        return "success"
    return "failure"


def evaluate(
    *,
    scheduled: dict[str, list[dict[str, Any]]],
    ci_runs: list[dict[str, Any]],
    ci_jobs: list[dict[str, Any]],
    now: datetime,
    max_age_days: float = 3.0,
) -> list[str]:
    """Return blocking findings; an empty list means evidence does not block readiness.

    Every scheduled run carries its ``jobs``. ``ci_jobs`` are the jobs of
    ``select_ci_run(ci_runs)``.
    """
    findings: list[str] = []
    for workflow, runs in sorted(scheduled.items()):
        completed = sorted(
            (
                run
                for run in runs
                if run.get("status") == "completed" and run.get("conclusion") != "cancelled"
            ),
            key=lambda run: _parse_time(run["createdAt"]),
            reverse=True,
        )
        if not completed:
            findings.append(f"{workflow}: no completed run on main; scheduled evidence is absent")
            continue
        latest = completed[0]
        if now - _parse_time(latest["createdAt"]) > timedelta(days=max_age_days):
            findings.append(
                f"{workflow}: newest run is older than {max_age_days:g} days "
                f"({latest.get('url')}); scheduled evidence is stale"
            )
        executed = next((run for run in completed if evidence_state(run) != "skipped"), None)
        if executed is None:
            findings.append(
                f"{workflow}: no run on main executed its evidence jobs (all skipped by the "
                "detector); scheduled evidence is absent"
            )
        elif evidence_state(executed) == "failure":
            findings.append(
                f"{workflow}: the newest evidence execution concluded "
                f"{executed.get('conclusion')!r} on {str(executed.get('headSha'))[:8]} "
                f"({executed.get('url')}); keep a linked open issue until a later run that "
                "executes the evidence jobs succeeds (detector-skipped runs do not count)"
            )
    ci_run = select_ci_run(ci_runs)
    pending = [run for run in ci_runs if run.get("status") != "completed"]
    for run in pending:
        findings.append(
            f"ci.yml main run {run.get('url')} is {run.get('status')!r}: no evidence yet for "
            f"{str(run.get('headSha'))[:8]}; wait for it to complete"
        )
    if ci_run is None:
        findings.append("ci.yml: no completed push run on main to inspect")
        return findings
    if ci_run.get("conclusion") != "success":
        findings.append(
            f"ci.yml main run {ci_run.get('url')} concluded {ci_run.get('conclusion')!r} on "
            f"{str(ci_run.get('headSha'))[:8]}"
        )
    if not ci_jobs:
        findings.append(
            f"ci.yml main run {ci_run.get('url')} has no jobs (startup failure); no evidence"
        )
    for job in ci_jobs:
        if job.get("conclusion") in BAD_JOB_CONCLUSIONS:
            findings.append(
                f"ci.yml main run {ci_run.get('url')}: job {job.get('name')!r} "
                f"concluded {job.get('conclusion')!r}"
            )
    return findings


def _gh_json(*args: str) -> Any:
    result = subprocess.run(["gh", *args], capture_output=True, text=True, check=True)
    return json.loads(result.stdout)


def _attach_jobs(repo: str, runs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Fetch jobs newest-first until a run that executed its evidence jobs is found."""
    completed = sorted(
        (r for r in runs if r.get("status") == "completed" and r.get("conclusion") != "cancelled"),
        key=lambda run: _parse_time(run["createdAt"]),
        reverse=True,
    )
    for run in completed:
        view = _gh_json("run", "view", str(run["databaseId"]), "--repo", repo, "--json", "jobs")
        run["jobs"] = view.get("jobs", [])
        if evidence_state(run) != "skipped":
            break
    return runs


def collect(repo: str) -> dict[str, Any]:
    scheduled = {
        workflow: _gh_json(
            "run", "list", "--repo", repo, "--workflow", workflow, "--branch", "main",
            "--limit", "10", "--json", RUN_FIELDS,
        )
        for workflow in SCHEDULED_WORKFLOWS
    }  # fmt: skip
    scheduled = {workflow: _attach_jobs(repo, runs) for workflow, runs in scheduled.items()}
    ci_runs = _gh_json(
        "run", "list", "--repo", repo, "--workflow", "ci.yml", "--branch", "main",
        "--event", "push", "--limit", "10", "--json", RUN_FIELDS,
    )  # fmt: skip
    selected = select_ci_run(ci_runs)
    ci_jobs: list[dict[str, Any]] = []
    if selected is not None:
        view = _gh_json(
            "run", "view", str(selected["databaseId"]), "--repo", repo, "--json", "jobs"
        )
        ci_jobs = view.get("jobs", [])
    return {"scheduled": scheduled, "ci_runs": ci_runs, "ci_jobs": ci_jobs}


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", default="CurateLabs/xyg")
    parser.add_argument("--max-age-days", type=float, default=3.0)
    parser.add_argument("--fixture", type=Path, help="replay recorded JSON instead of calling gh")
    parser.add_argument("--now", help="ISO timestamp override (fixture replay)")
    args = parser.parse_args(argv)
    try:
        if args.fixture is not None:
            data = json.loads(args.fixture.read_text(encoding="utf-8"))
        else:
            data = collect(args.repo)
    except (OSError, ValueError, subprocess.CalledProcessError) as exc:
        print(f"cannot collect evidence: {exc}", file=sys.stderr)
        return 2
    now = _parse_time(args.now) if args.now else datetime.now(UTC)
    findings = evaluate(
        scheduled=data["scheduled"],
        ci_runs=data.get("ci_runs", []),
        ci_jobs=data.get("ci_jobs", []),
        now=now,
        max_age_days=args.max_age_days,
    )
    if findings:
        print("Release readiness is BLOCKED by unresolved evidence:", file=sys.stderr)
        for finding in findings:
            print(f"  - {finding}", file=sys.stderr)
        return 1
    print("Scheduled evidence and the latest main CI run do not block release readiness.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
