#!/usr/bin/env python3
"""Fail the aggregate Release surfaces gate on failed or unexpected skipped jobs.

This module is also the single inventory of which ``ci.yml`` jobs are hard gates and
when each one applies (spec/process/production-readiness.md, "Hard and advisory
boundary"). ``scripts/verify_ci_workflow.py`` checks the workflow against it, so a job
cannot be added to, or dropped from, the required ``Release surfaces`` aggregate
without the inventory (and its tests) changing in the same commit.
"""

from __future__ import annotations

import argparse

SUCCESS = "success"
OPTIONAL_RESULTS = {"skipped", "success"}

# Hard on every event: run unconditionally and must succeed.
ALWAYS_HARD_JOBS = ("test", "wasm_assets", "wasm_foundation", "python_floor")
# Hard whenever the trusted-base classifier says the change touches a release surface
# (every push, merge_group and dispatch run is classified required); a skip while
# applicable is a failure, a skip while inapplicable (prose-only PR) is recorded and fine.
RELEASE_SURFACE_JOBS = (
    "browser_conformance",
    "sdist",
    "wheels",
    "install_without_rust",
    "authored_scene",
    "matplotlib_reference",
)
# Hard post-merge evidence: runs only for push/workflow_dispatch (cannot run before the
# merge queue promotes a change), must succeed there, and is inapplicable otherwise.
MAIN_EVIDENCE_JOBS = ("benchmark_vs", "benchmark_methodology", "benchmark")
MAIN_EVIDENCE_EVENTS = frozenset({"push", "workflow_dispatch"})
# ci.yml jobs that are deliberately not aggregate inputs. Empty on purpose: advisory
# work lives in scheduled workflows (codspeed, density-100m, ceiling) and never in ci.yml.
ADVISORY_CI_JOBS: tuple[str, ...] = ()
# Jobs that classify or aggregate rather than gate.
SUPPORT_JOBS = ("release_surface_changes", "release_surfaces")
HARD_JOBS = (*ALWAYS_HARD_JOBS, *RELEASE_SURFACE_JOBS, *MAIN_EVIDENCE_JOBS)


def applicable_jobs(*, event: str, required: bool) -> set[str]:
    """Hard jobs that must run (and succeed) for this event and classifier result."""
    jobs = set(ALWAYS_HARD_JOBS)
    if required:
        jobs.update(RELEASE_SURFACE_JOBS)
    if event in MAIN_EVIDENCE_EVENTS:
        jobs.update(MAIN_EVIDENCE_JOBS)
    return jobs


def verify(*, required: bool, results: dict[str, str], event: str = "pull_request") -> list[str]:
    errors: list[str] = []
    for name in sorted(set(results) - set(HARD_JOBS)):
        errors.append(f"unclassified job {name!r} passed to the Release surfaces aggregate")
    for name in ALWAYS_HARD_JOBS:
        if results.get(name) != SUCCESS:
            errors.append(f"{name} must succeed, got {results.get(name)!r}")
    for name in RELEASE_SURFACE_JOBS:
        result = results.get(name)
        if required and result != SUCCESS:
            errors.append(f"release-surface job {name} must succeed, got {result!r}")
        elif not required and result not in OPTIONAL_RESULTS:
            errors.append(f"optional release-surface job {name} failed with {result!r}")
    for name in MAIN_EVIDENCE_JOBS:
        result = results.get(name)
        if event in MAIN_EVIDENCE_EVENTS and result != SUCCESS:
            errors.append(f"main evidence job {name} must succeed on {event}, got {result!r}")
        elif event not in MAIN_EVIDENCE_EVENTS and result not in OPTIONAL_RESULTS:
            errors.append(f"main evidence job {name} must be skipped on {event}, got {result!r}")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--required", choices=("true", "false"), required=True)
    parser.add_argument(
        "--event",
        required=True,
        help="github.event_name of the run (pull_request, merge_group, push, workflow_dispatch)",
    )
    parser.add_argument("--job", action="append", default=[])
    args = parser.parse_args()
    results: dict[str, str] = {}
    for item in args.job:
        name, separator, result = item.partition("=")
        if not separator or not name or not result:
            parser.error(f"invalid --job value {item!r}; expected NAME=RESULT")
        if name in results:
            parser.error(f"duplicate --job value for {name!r}")
        results[name] = result
    errors = verify(required=args.required == "true", results=results, event=args.event)
    if errors:
        for error in errors:
            print(f"ERROR: {error}")
        return 1
    print(f"Release surfaces aggregate accepted every applicable job for {args.event}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
