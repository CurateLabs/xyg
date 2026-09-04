from __future__ import annotations

import pytest
import scripts.request_final_coderabbit as request_final_coderabbit
from scripts.request_final_coderabbit import (
    authorization_comment,
    has_existing_request,
    validate_candidate,
)

SHA = "a" * 40
REQUIRED = (
    "Test (Rust + Python + JS)",
    "Direct browser Rust/WASM foundation (wasm32-unknown-unknown)",
    "Python 3.11 floor",
    "Release surfaces",
)


def _candidate() -> tuple[dict, dict, dict, list[dict]]:
    pull = {"state": "open", "head": {"sha": SHA}, "mergeable": True, "mergeable_state": "clean"}
    runs = [
        {"name": name, "conclusion": "success", "details_url": "https://checks/1"}
        for name in REQUIRED
    ]
    runs.append({"name": "breadth", "conclusion": "skipped", "details_url": "https://checks/2"})
    return pull, {"total_count": len(runs), "check_runs": runs}, {"statuses": []}, []


def test_final_candidate_accepts_exact_green_merge_ready_head() -> None:
    pull, checks, statuses, threads = _candidate()

    assert (
        validate_candidate(pull, checks, statuses, threads, expected_head=SHA, current_run_id=99)
        == SHA
    )


def test_final_candidate_accepts_protection_blocked_green_head() -> None:
    pull, checks, statuses, threads = _candidate()
    pull["mergeable_state"] = "blocked"

    assert (
        validate_candidate(pull, checks, statuses, threads, expected_head=SHA, current_run_id=99)
        == SHA
    )


def test_final_candidate_rejects_missing_release_surface_aggregate() -> None:
    pull, checks, statuses, threads = _candidate()
    checks["check_runs"] = [
        check for check in checks["check_runs"] if check["name"] != "Release surfaces"
    ]
    checks["total_count"] -= 1

    with pytest.raises(ValueError, match="Release surfaces"):
        validate_candidate(pull, checks, statuses, threads, expected_head=SHA, current_run_id=99)


def test_final_candidate_does_not_depend_on_coderabbit_status() -> None:
    pull, checks, statuses, threads = _candidate()
    statuses["statuses"] = [{"context": "CodeRabbit", "state": "pending"}]

    assert (
        validate_candidate(pull, checks, statuses, threads, expected_head=SHA, current_run_id=99)
        == SHA
    )


def test_final_candidate_rejects_other_non_green_status() -> None:
    pull, checks, statuses, threads = _candidate()
    statuses["statuses"] = [{"context": "security", "state": "pending"}]

    with pytest.raises(ValueError, match="security"):
        validate_candidate(pull, checks, statuses, threads, expected_head=SHA, current_run_id=99)


def test_exact_head_request_marker_is_idempotent() -> None:
    comments = [
        {
            "author": {"login": "github-actions[bot]"},
            "body": authorization_comment(SHA),
        }
    ]

    assert has_existing_request(comments, SHA)
    assert not has_existing_request(comments, "b" * 40)


def test_authorization_comment_cannot_be_mistaken_for_a_review_command() -> None:
    body = authorization_comment(SHA)

    assert SHA in body
    assert "authenticated human" in body
    assert "@coderabbitai review" not in body


def test_spoofed_request_marker_is_not_accepted() -> None:
    comments = [{"author": {"login": "someone-else"}, "body": f"<!-- xyg-final-review:{SHA} -->"}]

    assert not has_existing_request(comments, SHA)


@pytest.mark.parametrize("invalid", [None, "stale", "closed", "conflicting", "failing"])
def test_existing_marker_only_skips_after_full_exact_head_validation(
    invalid: str | None, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("XYG_REF", "refs/heads/main")
    monkeypatch.setenv("XYG_REPOSITORY", "CurateLabs/xyg")
    monkeypatch.setenv("XYG_PR_NUMBER", "121")
    monkeypatch.setenv("XYG_CURRENT_RUN_ID", "99")
    monkeypatch.setenv("XYG_EXPECTED_HEAD", SHA)
    monkeypatch.setenv("GH_TOKEN", "token")
    calls: list[tuple[str, object]] = []

    pull, checks, statuses, _threads = _candidate()
    if invalid == "stale":
        pull["head"]["sha"] = "b" * 40
    elif invalid == "closed":
        pull["state"] = "closed"
    elif invalid == "conflicting":
        pull["mergeable"] = False
        pull["mergeable_state"] = "dirty"
    elif invalid == "failing":
        checks["check_runs"][0]["conclusion"] = "failure"
    pull_responses = [pull, pull]

    def request(url: str, _token: str, *, body: object = None) -> object:
        calls.append((url, body))
        if url.endswith("/pulls/121"):
            return pull_responses.pop(0)
        if "/check-runs" in url:
            return checks
        if url.endswith("/status"):
            return {"statuses": []}
        if url.endswith("/graphql"):
            return {
                "data": {
                    "repository": {
                        "pullRequest": {
                            "reviewThreads": {"totalCount": 0, "nodes": []},
                            "comments": {
                                "totalCount": 1,
                                "nodes": [
                                    {
                                        "author": {"login": "github-actions[bot]"},
                                        "body": f"<!-- xyg-final-review:{SHA} -->",
                                    }
                                ],
                            },
                        }
                    }
                }
            }
        raise AssertionError(f"unexpected request: {url} {body}")

    monkeypatch.setattr(request_final_coderabbit, "_request", request)

    expected_result = 0 if invalid is None else 1
    assert request_final_coderabbit.main() == expected_result
    output = capsys.readouterr()
    if invalid is None:
        assert "already authorized" in output.out
    else:
        assert "already authorized" not in output.out
    assert not any(url.endswith("/issues/121/comments") for url, _body in calls)


@pytest.mark.parametrize("comments", [None, [None], [{"body": "marker"}]])
def test_malformed_request_comments_fail_closed(comments: object) -> None:
    with pytest.raises(ValueError):
        has_existing_request(comments, SHA)


@pytest.mark.parametrize(
    "mutation", ["stale", "unmergeable", "draft", "pending", "missing", "thread"]
)
def test_final_candidate_fails_closed(mutation: str) -> None:
    pull, checks, statuses, threads = _candidate()
    expected = SHA
    if mutation == "stale":
        expected = "b" * 40
    elif mutation == "unmergeable":
        pull["mergeable_state"] = "behind"
    elif mutation == "draft":
        pull["draft"] = True
    elif mutation == "pending":
        checks["check_runs"].append(
            {"name": "another", "conclusion": None, "details_url": "https://checks/3"}
        )
        checks["total_count"] += 1
    elif mutation == "missing":
        checks["check_runs"].pop()
        checks["check_runs"].pop()
        checks["total_count"] -= 2
    else:
        threads.append({"isResolved": False})

    with pytest.raises(ValueError):
        validate_candidate(
            pull, checks, statuses, threads, expected_head=expected, current_run_id=99
        )
