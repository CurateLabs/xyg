"""The interaction probe's retry-and-headroom policy (CI reliability).

Headless-Chromium probes on shared runners have environmental failure modes
(virtual-time/wall-clock budget exhaustion, GPU init hiccups) that a fresh
launch resolves; a genuine client regression fails every attempt. These tests
pin that policy without launching a browser.
"""

from __future__ import annotations

from benchmarks import bench_interaction


def test_probe_relaunches_until_ok_and_reports_each_retry(monkeypatch, capsys):
    calls: list[dict] = []

    def fake_probe(html, *, marker, chromium, virtual_time_ms, timeout_s, hosted, wasm_ticks):
        calls.append(
            {
                "virtual_time_ms": virtual_time_ms,
                "timeout_s": timeout_s,
                "hosted": hosted,
                "wasm_ticks": wasm_ticks,
            }
        )
        if len(calls) >= 3:
            return {"status": "ok"}
        return {"status": "failed(timeout)"}

    monkeypatch.setattr(bench_interaction, "run_json_probe", fake_probe)

    result = bench_interaction._probe_with_retries(
        "<html/>", chromium=None, scenario="density_scatter_interaction", retries=2
    )

    assert result["status"] == "ok"
    assert len(calls) == 3
    # Retries are recorded, never silent.
    err = capsys.readouterr().err
    assert "retry 1/2 for density_scatter_interaction" in err
    assert "failed(timeout)" in err
    # Every attempt gets real hosted Rust ticks and shared-runner headroom.
    for call in calls:
        assert call["virtual_time_ms"] is None
        assert call["timeout_s"] == bench_interaction.PROBE_TIMEOUT_S
        assert call["hosted"] is True
        assert call["wasm_ticks"] is True


def test_zero_retries_keeps_first_failure(monkeypatch):
    calls: list[int] = []

    def fake_probe(html, **kwargs):
        calls.append(1)
        return {"status": "failed(timeout)"}

    monkeypatch.setattr(bench_interaction, "run_json_probe", fake_probe)

    result = bench_interaction._probe_with_retries(
        "<html/>", chromium=None, scenario="s", retries=0
    )

    assert result["status"] == "failed(timeout)"
    assert len(calls) == 1


def test_persistent_failure_exhausts_retries_and_keeps_last_status(monkeypatch):
    calls: list[int] = []

    def fake_probe(html, **kwargs):
        calls.append(1)
        return {"status": "failed(no probe title)"}

    monkeypatch.setattr(bench_interaction, "run_json_probe", fake_probe)

    result = bench_interaction._probe_with_retries(
        "<html/>", chromium=None, scenario="s", retries=2
    )

    assert result["status"] == "failed(no probe title)"
    assert len(calls) == 3  # 1 + 2 retries, then the real regression surfaces


def test_probe_headroom_exceeds_library_defaults():
    """The wall budget out-waits slow shared runners."""
    import inspect

    from benchmarks import _xy_browser

    sig = inspect.signature(_xy_browser.run_json_probe)
    assert sig.parameters["timeout_s"].default < bench_interaction.PROBE_TIMEOUT_S


def test_hosted_probe_preserves_memory_scrollbar_and_gl_launch_policy(
    monkeypatch,
):
    from benchmarks import _xy_browser

    commands: list[list[str]] = []

    class Completed:
        returncode = 0
        stdout = "<title>XY_TEST {&quot;status&quot;:&quot;ok&quot;}</title>"
        stderr = ""

    def fake_run(command, **kwargs):
        del kwargs
        commands.append(command)
        return Completed()

    monkeypatch.setattr(_xy_browser, "find_chromium", lambda _explicit: "/chrome")
    monkeypatch.setattr(_xy_browser.subprocess, "run", fake_run)
    monkeypatch.setattr(_xy_browser._xy_export, "copy_wasm_tick_assets", lambda _path: None)
    monkeypatch.setenv("XY_BENCH_HARDWARE_GL", "1")

    result = _xy_browser.run_json_probe(
        "<title></title>",
        marker="XY_TEST",
        chromium=None,
        hosted=True,
        wasm_ticks=True,
    )

    assert result == {"status": "ok"}
    command = commands.pop()
    assert "--hide-scrollbars" in command
    assert "--enable-precise-memory-info" in command
    assert "--use-angle=swiftshader" not in command
    assert "--enable-unsafe-swiftshader" not in command

    monkeypatch.delenv("XY_BENCH_HARDWARE_GL")
    result = _xy_browser.run_json_probe(
        "<title></title>",
        marker="XY_TEST",
        chromium=None,
        hosted=True,
    )

    assert result == {"status": "ok"}
    command = commands.pop()
    assert "--use-angle=swiftshader" in command
    assert "--enable-unsafe-swiftshader" in command
