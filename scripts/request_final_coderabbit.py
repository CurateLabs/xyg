"""Request one final CodeRabbit review only for a fully green PR candidate."""

from __future__ import annotations

import json
import os
import re
import sys
import urllib.error
import urllib.request
from typing import Any

_SHA = re.compile(r"[0-9a-f]{40}")
_REQUIRED_CHECKS = {
    "Test (Rust + Python + JS)",
    "Direct browser Rust/WASM foundation (wasm32-unknown-unknown)",
    "Python 3.11 floor",
    "Release surfaces",
}


def has_existing_request(comments: Any, head: str) -> bool:
    """Recognize only this workflow's exact-head marker from GitHub Actions."""
    if not isinstance(comments, list):
        raise ValueError("pull-request comment response is malformed")
    marker = f"<!-- xyg-final-review:{head} -->"
    for comment in comments:
        if not isinstance(comment, dict):
            raise ValueError("pull-request comment response contains a malformed comment")
        author = comment.get("author")
        if not isinstance(author, dict):
            raise ValueError("pull-request comment response contains a malformed author")
        body = comment.get("body")
        if (
            author.get("login") == "github-actions[bot]"
            and isinstance(body, str)
            and marker in body
        ):
            return True
    return False


def _required_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise ValueError(f"missing required environment variable {name}")
    return value


def _request(url: str, token: str, *, body: dict[str, Any] | None = None) -> Any:
    data = None if body is None else json.dumps(body).encode()
    request = urllib.request.Request(
        url,
        data=data,
        method="GET" if body is None else "POST",
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)


def validate_candidate(
    pull: Any,
    checks: Any,
    statuses: Any,
    threads: Any,
    *,
    expected_head: str,
    current_run_id: int,
) -> str:
    """Return the reviewed SHA or reject stale, incomplete, or unsafe state."""
    if not isinstance(pull, dict) or pull.get("state") != "open":
        raise ValueError("pull request is not open")
    head = pull.get("head", {}).get("sha") if isinstance(pull.get("head"), dict) else None
    if head != expected_head or not isinstance(head, str) or _SHA.fullmatch(head) is None:
        raise ValueError("pull request head does not match the requested exact SHA")
    # GitHub reports ``blocked`` while branch protection is waiting for the
    # very review this workflow requests. Required checks, statuses, and
    # unresolved threads are verified independently below.
    if (
        pull.get("draft") is True
        or pull.get("mergeable") is not True
        or pull.get("mergeable_state") not in {"clean", "blocked"}
    ):
        raise ValueError("pull request is not currently merge-ready")

    if not isinstance(checks, dict) or not isinstance(checks.get("check_runs"), list):
        raise ValueError("check-run response is malformed")
    if checks.get("total_count") != len(checks["check_runs"]):
        raise ValueError("check-run response is incomplete")
    successful: set[str] = set()
    for check in checks["check_runs"]:
        if not isinstance(check, dict):
            raise ValueError("check-run response contains a malformed check")
        details = check.get("details_url")
        if isinstance(details, str) and f"/runs/{current_run_id}/" in details:
            continue
        name = check.get("name")
        conclusion = check.get("conclusion")
        if not isinstance(name, str) or conclusion not in {"success", "skipped", "neutral"}:
            raise ValueError(f"check {name!r} is not green or intentionally skipped")
        if conclusion == "success":
            successful.add(name)
    missing = sorted(_REQUIRED_CHECKS - successful)
    if missing:
        raise ValueError(f"required PR checks are not green: {missing}")

    if not isinstance(statuses, dict) or not isinstance(statuses.get("statuses"), list):
        raise ValueError("commit-status response is malformed")
    bad_statuses = [
        status.get("context")
        for status in statuses["statuses"]
        if not isinstance(status, dict) or status.get("state") != "success"
    ]
    if bad_statuses:
        raise ValueError(f"commit statuses are not green: {bad_statuses}")

    if not isinstance(threads, list) or any(
        not isinstance(thread, dict) or thread.get("isResolved") is not True for thread in threads
    ):
        raise ValueError("pull request has unresolved or malformed review threads")
    return head


def main() -> int:
    try:
        if _required_env("XYG_REF") != "refs/heads/main":
            raise ValueError("final review workflow must be dispatched from main")
        repository = _required_env("XYG_REPOSITORY")
        if re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository) is None:
            raise ValueError("GitHub repository name is invalid")
        number = int(_required_env("XYG_PR_NUMBER"))
        current_run_id = int(_required_env("XYG_CURRENT_RUN_ID"))
        expected_head = _required_env("XYG_EXPECTED_HEAD")
        token = _required_env("GH_TOKEN")
        if number <= 0 or current_run_id <= 0 or _SHA.fullmatch(expected_head) is None:
            raise ValueError("final review inputs are invalid")
        api = f"https://api.github.com/repos/{repository}"
        pull = _request(f"{api}/pulls/{number}", token)
        checks = _request(f"{api}/commits/{expected_head}/check-runs?per_page=100", token)
        statuses = _request(f"{api}/commits/{expected_head}/status", token)
        owner, name = repository.split("/", 1)
        graphql = _request(
            "https://api.github.com/graphql",
            token,
            body={
                "query": """
query($owner:String!,$name:String!,$number:Int!){
  repository(owner:$owner,name:$name){pullRequest(number:$number){
    reviewThreads(first:100){totalCount nodes{isResolved}}
    comments(last:100){totalCount nodes{body author{login}}}
  }}
}
""",
                "variables": {"owner": owner, "name": name, "number": number},
            },
        )
        pull_graph = graphql.get("data", {}).get("repository", {}).get("pullRequest", {})
        thread_page = pull_graph.get("reviewThreads", {}) if isinstance(pull_graph, dict) else {}
        threads = thread_page.get("nodes") if isinstance(thread_page, dict) else None
        if not isinstance(thread_page, dict) or thread_page.get("totalCount") != len(threads or []):
            raise ValueError("review-thread response is incomplete")
        comment_page = pull_graph.get("comments", {}) if isinstance(pull_graph, dict) else {}
        comments = comment_page.get("nodes") if isinstance(comment_page, dict) else None
        if not isinstance(comment_page, dict) or comment_page.get("totalCount") != len(
            comments or []
        ):
            raise ValueError("pull-request comment response is incomplete")
        head = validate_candidate(
            pull,
            checks,
            statuses,
            threads,
            expected_head=expected_head,
            current_run_id=current_run_id,
        )
        refreshed = _request(f"{api}/pulls/{number}", token)
        if refreshed.get("head", {}).get("sha") != head:
            raise ValueError("pull request head changed during final-review verification")
        if has_existing_request(comments, head):
            print(f"final CodeRabbit review already requested for PR #{number} at {head}")
            return 0
        _request(
            f"{api}/issues/{number}/comments",
            token,
            body={"body": f"@coderabbitai review\n\n<!-- xyg-final-review:{head} -->"},
        )
        print(f"requested final CodeRabbit review for PR #{number} at {head}")
        return 0
    except (OSError, ValueError, TypeError, AttributeError, json.JSONDecodeError) as exc:
        print(f"Final CodeRabbit request failed closed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
