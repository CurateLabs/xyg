from __future__ import annotations

import io
import json
import urllib.request
from pathlib import Path

import pytest
from scripts.codspeed_should_run import (
    _successful_run_history,
    latest_successful_main_sha,
    main,
    should_run,
)


def _run(sha: str, *, run_id: int = 1, event: str = "schedule") -> dict[str, object]:
    return {
        "id": run_id,
        "event": event,
        "head_branch": "main",
        "head_sha": sha,
        "status": "completed",
        "conclusion": "success",
        "created_at": "2026-08-20T00:00:00Z",
    }


def test_runs_when_no_successful_nightly_or_manual_baseline_exists() -> None:
    sha = "a" * 40
    payload = {"workflow_runs": [_run("b" * 40, event="pull_request")]}

    assert should_run(sha, payload, 99)


def test_skips_only_when_latest_successful_main_sha_matches() -> None:
    sha = "a" * 40
    payload = {"workflow_runs": [_run(sha)]}

    assert not should_run(sha, payload, 99)
    assert should_run("b" * 40, payload, 99)


def test_manual_main_dispatch_forces_a_run_even_when_sha_is_unchanged() -> None:
    sha = "a" * 40

    assert should_run(sha, {"workflow_runs": [_run(sha)]}, 99, event="workflow_dispatch")


def test_non_schedule_or_manual_event_fails_closed() -> None:
    with pytest.raises(ValueError):
        should_run("a" * 40, {"workflow_runs": []}, 99, event="pull_request")


def test_manual_feature_dispatch_fails_before_api_access(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("XYG_EVENT_NAME", "workflow_dispatch")
    monkeypatch.setenv("XYG_REF", "refs/heads/feature/not-main")

    assert main() == 1
    assert "only by schedule/manual dispatch on main" in capsys.readouterr().err


def test_manual_main_dispatch_forces_without_actions_api(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    output = tmp_path / "output"
    monkeypatch.setenv("XYG_EVENT_NAME", "workflow_dispatch")
    monkeypatch.setenv("XYG_REF", "refs/heads/main")
    monkeypatch.setenv("XYG_CURRENT_SHA", "a" * 40)
    monkeypatch.setenv("XYG_CURRENT_RUN_ID", "123")
    monkeypatch.setenv("GITHUB_OUTPUT", str(output))

    def fail_urlopen(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("manual dispatch must not call the Actions API")

    monkeypatch.setattr("urllib.request.urlopen", fail_urlopen)

    assert main() == 0
    assert output.read_text(encoding="utf-8") == "should_run=true\n"


def test_history_queries_each_admitted_event_without_pr_run_starvation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: list[str] = []

    def response(request: urllib.request.Request, *, timeout: int) -> io.BytesIO:
        assert timeout == 30
        seen.append(request.full_url)
        event = "schedule" if "event=schedule" in request.full_url else "workflow_dispatch"
        run = _run("a" * 40 if event == "schedule" else "b" * 40, event=event)
        run["created_at"] = (
            "2026-08-19T00:00:00Z" if event == "schedule" else "2026-08-20T00:00:00Z"
        )
        return io.BytesIO(json.dumps({"workflow_runs": [run]}).encode())

    monkeypatch.setattr("urllib.request.urlopen", response)

    payload = _successful_run_history("CurateLabs/xyg", "token")

    assert [run["head_sha"] for run in payload["workflow_runs"]] == ["b" * 40, "a" * 40]
    assert len(seen) == 2
    assert all("per_page=1" in url and "branch=main" in url for url in seen)


def test_ignores_current_run_and_non_main_or_failed_runs() -> None:
    sha = "a" * 40
    payload = {
        "workflow_runs": [
            _run(sha, run_id=99),
            {**_run(sha, run_id=2), "head_branch": "feature"},
            {**_run(sha, run_id=3), "conclusion": "failure"},
            _run("b" * 40, run_id=4),
        ]
    }

    assert latest_successful_main_sha(payload, 99) == "b" * 40
    assert should_run(sha, payload, 99)


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"workflow_runs": {}},
        {"workflow_runs": [None]},
        {"workflow_runs": [{"id": 1}]},
        {"workflow_runs": [_run("not-a-sha")]},
    ],
)
def test_malformed_api_data_fails_closed(payload: object) -> None:
    with pytest.raises(ValueError):
        should_run("a" * 40, payload, 99)
