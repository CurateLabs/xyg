#!/usr/bin/env python3
"""Block release readiness on unresolved scheduled-evidence or main-CI failures (#1008).

Scheduled performance and browser evidence (CodSpeed, the density authority) stays
scheduled: it never runs on pull requests and is not a ``Release surfaces`` input. That
must not let a known, repeatedly failing run look like readiness. A release tracker, a
release authorization, or a "main is green" claim runs this check first:

* the latest completed run of each scheduled workflow on ``main`` must have succeeded
  and be recent; a failure blocks until a later run succeeds, and each blocking finding
  must be tracked by an open linked issue (close it only after that later green run);
* the latest push CI run on ``main`` must have no failed, cancelled, or timed-out job.

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
RUN_FIELDS = "databaseId,event,status,conclusion,headSha,createdAt,url"


def _parse_time(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def evaluate(
    *,
    scheduled: dict[str, list[dict[str, Any]]],
    ci_run: Optional[dict[str, Any]],
    ci_jobs: list[dict[str, Any]],
    now: datetime,
    max_age_days: float = 3.0,
) -> list[str]:
    """Return blocking findings; an empty list means evidence does not block readiness."""
    findings: list[str] = []
    for workflow, runs in sorted(scheduled.items()):
        completed = [
            run
            for run in runs
            if run.get("status") == "completed" and run.get("conclusion") != "cancelled"
        ]
        if not completed:
            findings.append(f"{workflow}: no completed run on main; scheduled evidence is absent")
            continue
        latest = max(completed, key=lambda run: _parse_time(run["createdAt"]))
        if latest.get("conclusion") != "success":
            findings.append(
                f"{workflow}: latest run concluded {latest.get('conclusion')!r} on "
                f"{str(latest.get('headSha'))[:8]} ({latest.get('url')}); keep a linked open issue "
                "until a later run on main succeeds"
            )
        elif now - _parse_time(latest["createdAt"]) > timedelta(days=max_age_days):
            findings.append(
                f"{workflow}: latest green run is older than {max_age_days:g} days "
                f"({latest.get('url')}); scheduled evidence is stale"
            )
    if ci_run is None:
        findings.append("ci.yml: no push run on main to inspect")
    for job in ci_jobs:
        if job.get("conclusion") in BAD_JOB_CONCLUSIONS:
            findings.append(
                f"ci.yml main run {(ci_run or {}).get('url')}: job {job.get('name')!r} "
                f"concluded {job.get('conclusion')!r}"
            )
    return findings


def _gh_json(*args: str) -> Any:
    result = subprocess.run(["gh", *args], capture_output=True, text=True, check=True)
    return json.loads(result.stdout)


def collect(repo: str) -> dict[str, Any]:
    scheduled = {
        workflow: _gh_json(
            "run", "list", "--repo", repo, "--workflow", workflow, "--branch", "main",
            "--limit", "10", "--json", RUN_FIELDS,
        )
        for workflow in SCHEDULED_WORKFLOWS
    }  # fmt: skip
    ci_runs = _gh_json(
        "run", "list", "--repo", repo, "--workflow", "ci.yml", "--branch", "main",
        "--event", "push", "--limit", "1", "--json", RUN_FIELDS,
    )  # fmt: skip
    ci_run = ci_runs[0] if ci_runs else None
    ci_jobs: list[dict[str, Any]] = []
    if ci_run is not None:
        view = _gh_json("run", "view", str(ci_run["databaseId"]), "--repo", repo, "--json", "jobs")
        ci_jobs = view.get("jobs", [])
    return {"scheduled": scheduled, "ci_run": ci_run, "ci_jobs": ci_jobs}


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
        ci_run=data.get("ci_run"),
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
