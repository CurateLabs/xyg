"""Bounded evidence contracts; actual browser runs are retained separately."""

from __future__ import annotations

import base64
import hashlib
import sys
from pathlib import Path

import numpy as np
import pytest
from benchmarks import _ux_comparison_data as data

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "benchmarks"))


def test_shared_source_preserves_original_stream_and_real_row_hash():
    n = 1000
    x, y = data.make_data(n)
    rng = np.random.default_rng(20260713)
    expected_x = rng.standard_normal(n, dtype=np.float32)
    expected_y = (
        rng.standard_normal(n, dtype=np.float32) * np.float32(1.2) + expected_x
    ) * np.float32(0.5)
    for i, (sx, sy) in enumerate(data.SENTINELS):
        expected_x[i], expected_y[i] = sx, sy
    np.testing.assert_array_equal(x, expected_x)
    np.testing.assert_array_equal(y, expected_y)
    identity = data.source_identity(x, y)
    assert identity["actual_rows"] == n
    assert identity["source_bytes"] == 8 * n
    assert identity["sha256_x_then_y"] == hashlib.sha256(x.tobytes() + y.tobytes()).hexdigest()
    y[-1] += 1
    assert data.source_identity(x, y)["sha256_x_then_y"] != identity["sha256_x_then_y"]
    with pytest.raises(ValueError, match="five rows"):
        data.make_data(4)


def test_transport_accounts_utf8_binary_both_directions_and_phase_delta():
    pytest.importorskip("websocket")
    from benchmarks.bench_ux import SocketBytes, byte_delta

    counter = SocketBytes()
    before = counter.snapshot()
    counter.record("Network.webSocketFrameSent", {"opcode": 1, "payloadData": "é"})
    counter.record(
        "Network.webSocketFrameReceived",
        {"opcode": 2, "payloadData": base64.b64encode(b"\0abc").decode()},
    )
    counter.record("Network.webSocketFrameSent", {"opcode": 9, "payloadData": "ignored ping"})
    after = counter.snapshot()
    assert after["to_host"]["json_bytes"] == 2
    assert after["from_host"]["binary_frame_bytes"] == 4
    assert after["total_bytes"] == 6
    assert before["total_bytes"] == 0  # snapshots do not alias live counters
    assert byte_delta(after, before) == after
    with pytest.raises(ValueError, match="non-monotonic"):
        byte_delta(before, after)


def test_datashader_raster_all_rows_mass_bounds_orientation_and_png():
    pytest.importorskip("datashader")
    pd = pytest.importorskip("pandas")
    pytest.importorskip("tornado")
    from benchmarks._ux_plotly_aggregate_host import aggregate

    # Deliberately asymmetric, with duplicates and points on each extent edge.
    frame = pd.DataFrame({"x": [0.0, 0.0, 1.0, 2.0, 3.0], "y": [0.0, 0.0, 2.0, 3.0, 1.0]})
    for domain, count in [
        ([0.0, 3.0, 0.0, 3.0], 5),
        ([0.0, 1.0, 0.0, 2.0], 3),
        ([4.0, 5.0, 4.0, 5.0], 0),
    ]:
        result = aggregate(frame, domain, width=12, height=8)
        assert result["oracle"] == {"count": count, "grid_mass": count, "passed": True}
        png = base64.b64decode(result["source"].split(",", 1)[1])
        assert png.startswith(b"\x89PNG\r\n\x1a\n")
        assert hashlib.sha256(png).hexdigest() == result["png_sha256"]
        assert result["grid_shape"] == [8, 12]
        if count == 5:
            import io

            from PIL import Image

            rgba = np.asarray(Image.open(io.BytesIO(png)))
            # to_pil flips data-space y upward to image-space top-down.
            assert rgba[-1, 0, 3] > 0  # x=0,y=0 at bottom left
            assert rgba[0, 8, 3] > 0  # x=2,y=3 at top
            assert rgba[0, 0, 3] == 0
    with pytest.raises(ValueError, match="finite increasing"):
        aggregate(frame, [0.0, 0.0, 0.0, 1.0])


def test_comparison_arms_keep_raw_plotly_and_disclose_source_provenance():
    pytest.importorskip("websocket")
    from benchmarks.bench_ux import ARMS, provenance

    assert {
        "plotly",
        "plotly-aggregate",
        "datashader",
        "datashader-aggregate",
        "xy-density",
    } <= set(ARMS)
    hashes = provenance()
    assert (
        hashes["benchmarks/_ux_comparison_data.py"]
        == hashlib.sha256((ROOT / "benchmarks/_ux_comparison_data.py").read_bytes()).hexdigest()
    )
    assert hashes["benchmarks/_ux_plotly_aggregate_host.py"]
    assert hashes["benchmarks/requirements-ci.lock"]


def test_retained_bounded_cells_transport_and_oracle_evidence():
    """Validate recorded evidence, not a replacement for a browser execution."""
    import json

    directory = ROOT / "benchmarks/results/live-aggregation-2026-10-24"
    report = json.loads((directory / "bounded.json").read_text())
    rows = report["results"]
    assert {(r["arm"], r["n"]) for r in rows} == {
        (arm, n) for arm in report["arms"] for n in report["sizes"]
    }
    assert len(rows) == 18
    assert max(report["sizes"]) == 1_000_000
    assert report["environment"]["package_versions"]["datashader"] == "0.19.1"
    assert report["environment"]["git"]["dirty"] is True
    for row in rows:
        assert row["source_matches_shared_workload"] is True
        assert row["source"] == report["sources"][str(row["n"])]
        assert row["source"]["actual_rows"] == row["n"]
        assert row["source"]["source_bytes"] == row["n"] * 8
        if row["status"] != "ok":
            assert row["arm"] == "plotly"
            assert row["status"] in {"memory_limit", "unsupported_svg_readback"}
            assert "visible_complete_ms" not in row
            continue
        assert row["render_stable"] is True
        assert 0 < row["final_span_fraction"] <= 0.5
        assert row["host_peak_rss_bytes"] > 0
        assert row["browser_peak_rss_bytes"] > 0
        checkpoints = row["transport"]["checkpoints"]
        for name in ("visible-complete", "settle-complete", "terminal"):
            snap = checkpoints[name]
            cdp = snap["cdp_application_bytes"]
            assert cdp["total_bytes"] == sum(
                cdp[d]["total_bytes"] for d in ("to_host", "from_host")
            )
            if row["arm"] in {"xy-exact", "xy-density", "plotly-aggregate"}:
                # Independent browser CDP, page API and host all agree in this run.
                assert snap["applicationBytes"] == cdp
                host = snap["host_application_bytes"]
                assert {k: host[k] for k in cdp} == cdp
        delta = row["transport"]["warm_gesture_cdp_delta"]
        assert delta["total_bytes"] == (
            checkpoints["settle-complete"]["cdp_application_bytes"]["total_bytes"]
            - checkpoints["visible-complete"]["cdp_application_bytes"]["total_bytes"]
        )
        if row["arm"] == "plotly-aggregate":
            evidence = checkpoints["settle-complete"]["evidence"]
            assert evidence["revision"] > 0
            assert evidence["applied"] == evidence["revision"]
            assert evidence["raster"]["domain"] == evidence["domain"]
            frames = checkpoints["terminal"]["host_application_bytes"]["frames"]
            assert len(frames) >= 2
            assert frames[0]["oracle"]["count"] == row["n"]
            assert all(
                f["oracle"]["passed"] and f["oracle"]["count"] == f["oracle"]["grid_mass"]
                for f in frames
            )
        if row["arm"] == "datashader-aggregate":
            evidence = checkpoints["settle-complete"]["evidence"]
            d = evidence["domain"]
            assert any(
                np.allclose(
                    [r["x"], r["y"], r["dw"], r["dh"]],
                    [d["x0"], d["y0"], d["x1"] - d["x0"], d["y1"] - d["y0"]],
                    rtol=1e-6,
                    atol=1e-8,
                )
                for r in evidence["rasters"]
            )
    # These files are the retained outputs, not generated from timing headlines.
    for line in (directory / "SHA256SUMS").read_text().splitlines():
        digest, relative = line.split("  ", 1)
        assert hashlib.sha256((directory / relative).read_bytes()).hexdigest() == digest
