"""Fail-closed gate for the nightly, main-only CodSpeed workflow."""

from __future__ import annotations

import json
import os
import re
import sys
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

_SHA = re.compile(r"[0-9a-f]{40}")
_ALLOWED_EVENTS = {"schedule", "workflow_dispatch"}


def latest_successful_main_sha(payload: Any, current_run_id: int) -> str | None:
    """Return the newest completed main benchmark SHA, rejecting malformed API data."""
    if not isinstance(payload, dict) or not isinstance(payload.get("workflow_runs"), list):
        raise ValueError("GitHub Actions response is missing workflow_runs")
    for run in payload["workflow_runs"]:
        if not isinstance(run, dict):
            raise ValueError("GitHub Actions response contains a malformed run")
        required = {
            "id",
            "event",
            "head_branch",
            "head_sha",
            "status",
            "conclusion",
            "created_at",
        }
        if not required.issubset(run):
            raise ValueError("GitHub Actions response contains an incomplete run")
        if run["id"] == current_run_id:
            continue
        if (
            run["event"] in _ALLOWED_EVENTS
            and run["head_branch"] == "main"
            and run["status"] == "completed"
            and run["conclusion"] == "success"
        ):
            sha = run["head_sha"]
            if not isinstance(sha, str) or _SHA.fullmatch(sha) is None:
                raise ValueError("successful main benchmark has an invalid head SHA")
            return sha
    return None


def should_run(
    current_sha: str, payload: Any, current_run_id: int, *, event: str = "schedule"
) -> bool:
    """Run changed scheduled SHAs and every explicit main-branch manual request."""
    if _SHA.fullmatch(current_sha) is None:
        raise ValueError("current main SHA is invalid")
    if event == "workflow_dispatch":
        return True
    if event != "schedule":
        raise ValueError("unsupported CodSpeed event")
    return latest_successful_main_sha(payload, current_run_id) != current_sha


def _required_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise ValueError(f"missing required environment variable {name}")
    return value


def _successful_run_history(repository: str, token: str) -> dict[str, list[Any]]:
    """Fetch the latest success for each admitted event without PR-run starvation."""
    if re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository) is None:
        raise ValueError("GitHub repository name is invalid")
    runs: list[Any] = []
    for event in sorted(_ALLOWED_EVENTS):
        query = urllib.parse.urlencode(
            {"branch": "main", "event": event, "status": "success", "per_page": "1"}
        )
        request = urllib.request.Request(
            f"https://api.github.com/repos/{repository}/actions/workflows/codspeed.yml/runs?{query}",
            headers={
                "Accept": "application/vnd.github+json",
                "Authorization": f"Bearer {token}",
                "X-GitHub-Api-Version": "2022-11-28",
            },
        )
        with urllib.request.urlopen(request, timeout=30) as response:
            payload = json.load(response)
        if not isinstance(payload, dict) or not isinstance(payload.get("workflow_runs"), list):
            raise ValueError("GitHub Actions response is missing workflow_runs")
        runs.extend(payload["workflow_runs"])
    if any(not isinstance(run, dict) or not isinstance(run.get("created_at"), str) for run in runs):
        raise ValueError("GitHub Actions response contains invalid run timestamps")
    runs.sort(key=lambda run: run["created_at"], reverse=True)
    return {"workflow_runs": runs}


def main() -> int:
    try:
        event = _required_env("XYG_EVENT_NAME")
        ref = _required_env("XYG_REF")
        if event not in _ALLOWED_EVENTS or ref != "refs/heads/main":
            raise ValueError("CodSpeed may run only by schedule/manual dispatch on main")
        current_sha = _required_env("XYG_CURRENT_SHA")
        current_run_id = int(_required_env("XYG_CURRENT_RUN_ID"))
        output = Path(_required_env("GITHUB_OUTPUT"))
        if _SHA.fullmatch(current_sha) is None or current_run_id <= 0:
            raise ValueError("current workflow identity is invalid")
        if event == "workflow_dispatch":
            decision = True
        else:
            repository = _required_env("XYG_REPOSITORY")
            token = _required_env("GH_TOKEN")
            payload = _successful_run_history(repository, token)
            decision = should_run(current_sha, payload, current_run_id, event=event)
        with output.open("a", encoding="utf-8") as stream:
            stream.write(f"should_run={'true' if decision else 'false'}\n")
        print("main changed; running CodSpeed" if decision else "main unchanged; skipping CodSpeed")
        return 0
    except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
        print(f"CodSpeed change detection failed closed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
