"""Manual materialized-100M walltime rows, with setup outside measurement.

The normal benchmark glob discovers these four rows, but explicitly skips them
unless XYG_FILTER_PERF_SOURCE names the materialized fixture. Never generate a
100M source during ordinary CI or silently substitute a smaller dataset.
See spec/benchmarks/methodology.md for the CodSpeed command and measurement scope.
"""

import json
import os
import queue
import subprocess
import threading
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def dashboard(tmp_path_factory):
    source = os.environ.get("XYG_FILTER_PERF_SOURCE")
    if not source:
        pytest.skip("manual materialized-100M source not configured; no performance credit")
    manifest = json.loads((Path(source) / "manifest.json").read_text())
    assert manifest["rows"] == 100_000_000, "these rows require all 100M source rows"
    assert os.environ.get("XYG_CHROMIUM"), "explicit XYG_CHROMIUM is required"
    assert os.environ.get("XYG_FILTER_ACTIVE_CELLS", "pixel") == "pixel"
    assert os.environ.get("XYG_FILTER_BUDGET_MIB", "256") == "256"
    output = Path(
        os.environ.get("XYG_FILTER_PERF_OUTPUT") or tmp_path_factory.mktemp("filter-perf")
    ).resolve()
    output.mkdir(parents=True, exist_ok=True)
    stderr = (output / "host.stderr.log").open("w")
    process = subprocess.Popen(
        [
            os.environ.get("XYG_NODE", "node"),
            str(Path(__file__).with_name("bench_filter_dashboard.mjs")),
            source,
            str(output),
        ],
        cwd=ROOT,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=stderr,
        text=True,
        bufsize=1,
    )
    replies = queue.Queue()

    def read_replies():
        try:
            for line in process.stdout:
                replies.put(json.loads(line))
        except BaseException as error:
            replies.put({"error": repr(error)})
        finally:
            replies.put({"error": "host stdout closed"})

    reader = threading.Thread(target=read_replies, daemon=True)
    reader.start()

    protocol_failed = False

    def reply(timeout=60):
        nonlocal protocol_failed
        try:
            value = replies.get(timeout=timeout)
        except queue.Empty as error:
            raise AssertionError(f"Host deadline; see {output / 'host.stderr.log'}") from error
        if "error" in value:
            protocol_failed = True
            raise AssertionError(value)
        return value

    def request(op):
        process.stdin.write(json.dumps({"op": op}) + "\n")
        process.stdin.flush()
        return reply()

    ready = False
    try:
        initial = reply(timeout=300)
        assert initial["ready"] is True
        ready = True
        assert initial["setup"]["rows"] == 100_000_000
        assert initial["setup"]["cells"] == initial["setup"]["plot"]["w"]
        assert initial["setup"]["passiveGrid"] == [100, 100]
        assert initial["setup"]["budgetMiB"] == 256
        # Correctness and lazy first-use initialization are outside measurement.
        for _ in range(2):
            result = request("update")
            assert result["rowsRead"] == "0" and result["builds"] == 1
        yield request
    finally:
        try:
            if ready and not protocol_failed and process.poll() is None:
                assert request("close") == {"closed": True}
                assert process.wait(timeout=30) == 0
            elif process.poll() is None:
                # Let the host's finally block close its browser and native owner.
                process.wait(timeout=30)
        finally:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=15)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=15)
            process.stdin.close()
            process.stdout.close()
            reader.join(timeout=5)
            stderr.close()


@pytest.mark.parametrize("phase", ["query", "density", "cached", "update"])
def test_five_view_indexed_update(benchmark, dashboard, phase):
    result = benchmark(dashboard, phase)
    assert result["rowsRead"] == "0"
    assert result["tier"] == "3"
    assert result["builds"] == 1
