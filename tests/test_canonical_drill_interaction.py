"""Channel-preserving canonical drills before resident/spilled density returns."""

from __future__ import annotations

import struct
from typing import Any

import numpy as np
import pytest

import xyg
from xyg import channels, interaction, kernels
from xyg.config import DRILL_HISTORY_KEEP

CONTROL = struct.pack("<4sIQdiI", b"XYDC", 1, 0, -1.0, -1, 0)


def configure(monkeypatch):
    # Small grids exercise real spill/I/O/paint, with production row thresholds.
    monkeypatch.setattr(interaction, "PYRAMID_MIN_POINTS", 1)
    monkeypatch.setattr(interaction, "PYRAMID_BASE_DIM", 256)


def make_chart(monkeypatch, kind="continuous", *, spill=True, n=600_000):
    configure(monkeypatch)
    rows = np.arange(n)
    x = rows.astype(np.float64) / (n - 1)
    y = ((rows * 31) % n).astype(np.float64) / (n - 1)
    rgba = np.column_stack(
        (rows % 256, (rows * 7) % 256, (rows * 13) % 256, 64 + rows % 192)
    ).astype(np.uint8)
    color = {
        "continuous": x,
        "custom": x,
        "categorical": np.where(rows % 2, "odd", "even"),
        "direct_rgba": rgba.astype(float) / 255,
    }[kind]
    fig = xyg.scatter_chart(
        xyg.scatter(
            x,
            y,
            color=color,
            colormap=["#ff0044", "#0066ff"] if kind == "custom" else "viridis",
            size=x,
            size_range=(2, 12),
            stroke=rgba.astype(float) / 255,
            stroke_width=1 + x,
            opacity=0.3 + 0.5 * x,
            symbol=np.where(rows % 2, "square", "circle"),
            density=True,
            pyramid_spill=spill,
        )
    ).figure()
    trace = fig.traces[0]
    interaction._ensure_pyramid(trace)
    return fig, trace, x, y, rgba


def forbid(*args, **kwargs):
    raise AssertionError("unbounded range/index/full-channel route used by canonical drill")


@pytest.mark.parametrize("kind", ["continuous", "custom", "categorical", "direct_rgba"])
@pytest.mark.parametrize("keyed", [False, True])
def test_spilled_channels_identity_and_legacy_xydc_parity(monkeypatch, tmp_path, kind, keyed):
    from test_spatial import _write_index
    from xyg._spatial import SpatialIndex

    fig, trace, x, y, rgba = make_chart(monkeypatch, kind)
    store = interaction._tile_store_of(trace)
    pointers = (trace.x.values.ctypes.data, trace.y.values.ctypes.data)
    # The legacy row-major f32 index deliberately has a different order.
    trace._spatial_index = SpatialIndex.load(_write_index(tmp_path, 16, (0, 1, 0, 1), x, y))
    assert not np.array_equal(trace._spatial_index.lon, x.astype(np.float32))
    monkeypatch.setattr(kernels, "range_indices", forbid)
    monkeypatch.setattr(interaction, "select_range", forbid)
    monkeypatch.setattr(interaction, "_ship_index_points", forbid)
    monkeypatch.setattr(interaction, "trace_bin_colors", forbid)
    window = (0.20, 0.22, 0.20, 0.40)
    try:
        reply, buffers = fig.density_view(
            0, *window, 320, 240, tile_cache=CONTROL if keyed else None
        )
        entry = reply["traces"][0]
        assert (entry["mode"], entry["tier"], entry["reduction"], entry["binning"]) == (
            "points",
            "direct",
            "none",
            "canonical-points",
        )
        query = entry["canonical_query"]
        expected_view = (x >= window[0]) & (x <= window[1]) & (y >= window[2]) & (y <= window[3])
        assert query["status"] == "complete" and query["count"] == int(expected_view.sum())
        assert query["candidate_rows"] == query["rows_read"] < len(x)
        assert query["read_bytes"] == query["rows_read"] * 16
        (x0, x1), (y0, y1) = entry["x_range"], entry["y_range"]
        expected = np.flatnonzero((x >= x0) & (x <= x1) & (y >= y0) & (y <= y1))
        np.testing.assert_array_equal(trace.shipped_sel, expected)
        assert entry["visible"] == len(expected) <= 200_000
        assert entry["lod_blend"] == pytest.approx(query["count"] / 200_000)
        assert entry["size"]["domain"] == [0.0, 1.0]
        assert entry["size"]["range_px"] == [2.0, 12.0]
        np.testing.assert_array_equal(
            np.frombuffer(buffers[entry["size"]["buf"]], dtype=np.uint8),
            channels.quantize_unit_u8(x[expected], (0, 1)),
        )
        if kind in {"continuous", "custom"}:
            assert entry["color"]["domain"] == [0.0, 1.0]
            np.testing.assert_array_equal(
                np.frombuffer(buffers[entry["color"]["buf"]], dtype=np.uint8),
                channels.quantize_unit_u8(x[expected], (0, 1)),
            )
            if kind == "custom":
                assert entry["color"]["colormap"] == [[255, 0, 68], [0, 102, 255]]
        elif kind == "categorical":
            np.testing.assert_array_equal(
                np.frombuffer(buffers[entry["color"]["buf"]], dtype=np.uint8),
                trace.color_ch.codes[expected],
            )
        elif kind == "direct_rgba":
            np.testing.assert_array_equal(
                np.frombuffer(buffers[entry["color"]["buf"]], dtype=np.uint8).reshape(-1, 4),
                rgba[expected],
            )
        np.testing.assert_array_equal(
            np.frombuffer(buffers[entry["stroke"]["buf"]], dtype=np.uint8).reshape(-1, 4),
            rgba[expected],
        )
        assert set(entry["channels"]) >= {"stroke_width", "opacity", "symbol"}
        for key in ("stroke_width", "opacity"):
            np.testing.assert_allclose(
                np.frombuffer(buffers[entry["channels"][key]["buf"]], dtype=np.float32),
                trace.style_channels[key].values[expected],
            )
        ref = entry["x"]
        np.testing.assert_allclose(
            np.frombuffer(buffers[ref["buf"]], dtype=np.float32).astype(float) + ref["offset"],
            x[expected],
            atol=1e-8,
        )
        for index in (0, len(expected) // 2, len(expected) - 1):
            picked = fig.pick(0, index, drill_seq=entry["drill_seq"])
            assert picked["index"] == expected[index]
            assert picked["x"] == x[expected[index]]
            assert picked["y"] == y[expected[index]]
        np.testing.assert_array_equal(fig.to_shipped_indices(0, expected[:3]), [0, 1, 2])
        assert pointers == (trace.x.values.ctypes.data, trace.y.values.ctypes.data)
        assert interaction._tile_store_of(trace) == store
        # Full-domain zoom-out must still paint the colored source tiles.
        out, out_buffers = fig.density_view(0, 0, 1, 0, 1, 320, 240, tile_cache=CONTROL)
        assert out["traces"][0]["mode"] == "density"
        assert out_buffers[0][:4] == b"XYDT"
        assert interaction._tile_store_of(trace) == store
    finally:
        interaction._free_pyramid(trace)


@pytest.mark.parametrize("spill", [False, True])
@pytest.mark.parametrize("upper", [1.0, 0.55])
def test_wide_colored_views_do_not_admit_canonical_reads(monkeypatch, spill, upper):
    fig, trace, *_ = make_chart(monkeypatch, spill=spill)
    monkeypatch.setattr(kernels, "canonical_drill_query", forbid)
    monkeypatch.setattr(kernels, "range_indices", forbid)
    try:
        # Actual source estimate ~330k exercises the old 300k–345k gap.
        reply, _ = fig.density_view(0, 0, upper, 0, 1, 16, 16, tile_cache=CONTROL)
        assert reply["traces"][0]["mode"] == "density"
    finally:
        interaction._free_pyramid(trace)


def test_malformed_controls_reject_before_lazy_build_or_drill_mutation(monkeypatch):
    configure(monkeypatch)
    fig = xyg.scatter_chart(
        xyg.scatter([0.0, 1.0], [0.0, 1.0], color=[0.0, 1.0], density=True, pyramid_spill=True)
    ).figure()
    trace = fig.traces[0]
    monkeypatch.setattr(interaction, "_ensure_pyramid", forbid)
    before = (trace.drill_mode, trace.drill_seq, trace.shipped_sel, dict(trace.drill_history))
    controls: tuple[Any, ...] = (
        b"XYDC",
        CONTROL + b"x",
        b"WRNG" + CONTROL[4:],
        b"x" * 3105,
        {"keys": []},
    )
    for control in controls:
        with pytest.raises(ValueError, match="tile painter control"):
            fig.density_view(0, 0, 0.1, 0, 0.1, 320, 240, tile_cache=control)
        assert (trace.drill_mode, trace.drill_seq, trace.shipped_sel, trace.drill_history) == before
        assert trace._tile_store is None and trace._pyr_handle is None


@pytest.mark.parametrize("keyed", [False, True])
def test_overflow_keeps_mapping_and_cannot_fall_back_to_n_sized_scan(monkeypatch, keyed):
    configure(monkeypatch)
    monkeypatch.setattr(interaction, "DRILL_PAD_TARGETS", ())
    x = np.full(300_000, 0.5)
    x[:2] = [0, 1]
    fig = xyg.scatter_chart(
        xyg.scatter(x, x.copy(), color=x.copy(), density=True, pyramid_spill=True)
    ).figure()
    trace = fig.traces[0]
    try:
        first, _ = fig.density_view(0, 0, 0.001, 0, 0.001, 128, 96)
        assert first["traces"][0]["mode"] == "points"
        seq, sel, history = trace.drill_seq, trace.shipped_sel, dict(trace.drill_history)
        monkeypatch.setattr(kernels, "range_indices", forbid)
        reply, _ = fig.density_view(
            0, 0.49, 0.51, 0.49, 0.51, 128, 96, tile_cache=CONTROL if keyed else None
        )
        entry = reply["traces"][0]
        assert entry["mode"] == "density" and entry["reduction"] == "pyramid-count"
        assert entry["canonical_query"]["status"] == "overflow"
        assert entry["canonical_query"]["count"] is None
        assert trace.drill_mode and trace.drill_seq == seq and trace.shipped_sel is sel
        assert trace.drill_history == history
    finally:
        interaction._free_pyramid(trace)


def test_threshold_hysteresis_padding_fallback_history_and_append(monkeypatch):
    configure(monkeypatch)
    monkeypatch.setattr(interaction, "DRILL_PAD_TARGETS", ())
    n = 300_000
    x = np.arange(n, dtype=float)
    fig = xyg.scatter_chart(
        xyg.scatter(x, x.copy(), color=x.copy(), density=True, pyramid_spill=True)
    ).figure()
    trace = fig.traces[0]
    try:
        first, _ = fig.density_view(0, 0, 199_999, 0, 199_999, 128, 96, tile_cache=CONTROL)
        a = first["traces"][0]
        assert a["mode"] == "points" and a["visible"] == 200_000
        assert a["padding"] == {"applied": False, "fallback": "raw-view", "queries": []}
        second, _ = fig.density_view(0, 0, 210_000, 0, 210_000, 128, 96, tile_cache=CONTROL)
        assert second["traces"][0]["mode"] == "points"
        assert second["traces"][0]["visible"] == 210_001
        picked = fig.pick(0, 12, drill_seq=a["drill_seq"])
        assert picked is not None and picked["index"] == 12
        for step in range(DRILL_HISTORY_KEEP):
            fig.density_view(0, 1 + step, 100 + step, 1 + step, 100 + step, 128, 96)
        assert fig.pick(0, 12, drill_seq=a["drill_seq"]) is None
        current_seq = trace.drill_seq
        old = interaction._tile_store_of(trace)
        assert old is not None
        fig.append(0, [float(n)], [float(n)], color=[float(n)])
        assert trace.drill_history == {}
        assert fig.pick(0, 0, drill_seq=current_seq) is None
        assert kernels.tile_store_stats(old) is None
        reply, _ = fig.density_view(0, n - 1, n, n - 1, n, 128, 96)
        assert reply["traces"][0]["mode"] == "points"
        assert trace.shipped_sel is not None and trace.shipped_sel[-1] == n
    finally:
        interaction._free_pyramid(trace)


@pytest.mark.parametrize("spill", [False, True])
@pytest.mark.parametrize("active", [False, True])
@pytest.mark.parametrize("refusal", ["overflow", "scan-budget"])
def test_refused_query_with_unavailable_aggregate_never_scans_or_changes_drill(
    monkeypatch, spill, active, refusal
):
    configure(monkeypatch)
    monkeypatch.setattr(interaction, "DRILL_PAD_TARGETS", ())
    x = np.full(300_000, 0.5)
    x[:2] = [0, 1]
    fig = xyg.scatter_chart(
        xyg.scatter(x, x.copy(), color=x.copy(), density=True, pyramid_spill=spill)
    ).figure()
    trace = fig.traces[0]
    try:
        interaction._ensure_pyramid(trace)
        if active:
            fig.density_view(0, 0, 0.001, 0, 0.001, 128, 96)
        seq, sel, mode = trace.drill_seq, trace.shipped_sel, trace.drill_mode
        if refusal == "scan-budget":
            # Native preflight refusal is proved at the ABI seam; inject its
            # outcome here to exercise the aggregate-failure handoff.
            monkeypatch.setattr(
                kernels,
                "canonical_drill_query",
                lambda *a, **kw: {
                    "status": "scan-budget",
                    "count": None,
                    "indices": np.empty(0, dtype=np.uint32),
                    "candidate_rows": 80_000_001,
                    "candidate_chunks": 1221,
                    "rows_read": 0,
                    "read_bytes": 0,
                    "point_cap": 200_000,
                    "scan_row_budget": 80_000_000,
                },
            )
        monkeypatch.setattr(kernels, "tile_store_compose_color", lambda *a: None)
        monkeypatch.setattr(kernels, "pyramid_compose_color", lambda *a: None)
        monkeypatch.setattr(kernels, "range_indices", forbid)
        monkeypatch.setattr(kernels, "bin_2d", forbid)
        reply, buffers = fig.density_view(0, 0.49, 0.51, 0.49, 0.51, 128, 96)
        assert reply["traces"] == [] and not buffers
        assert reply["canonical_query"]["status"] == refusal
        assert reply["canonical_query"]["count"] is None
        assert trace.drill_seq == seq and trace.shipped_sel is sel and trace.drill_mode == mode
    finally:
        interaction._free_pyramid(trace)


@pytest.mark.parametrize("kind", ["size", "stroke", "style"])
def test_isolated_point_channel_restores_without_legacy_index(monkeypatch, kind):
    configure(monkeypatch)
    x = np.linspace(0.0, 1.0, 300_000)
    fig = xyg.scatter_chart(
        xyg.scatter(
            x,
            x.copy(),
            color="#123456",
            density=True,
            pyramid_spill=True,
            size=x if kind == "size" else 4,
            stroke=np.tile([1.0, 0.0, 0.0, 0.5], (len(x), 1)) if kind == "stroke" else None,
            opacity=x if kind == "style" else 0.8,
        )
    ).figure()
    trace = fig.traces[0]
    monkeypatch.setattr(kernels, "range_indices", forbid)
    monkeypatch.setattr(interaction, "_ship_index_points", forbid)
    try:
        reply, _ = fig.density_view(0, 0.2, 0.22, 0.2, 0.22, 128, 96, tile_cache=CONTROL)
        entry = reply["traces"][0]
        assert entry["binning"] == "canonical-points"
        assert entry["color"]["mode"] == "constant"
        assert entry["size"]["mode"] == ("continuous" if kind == "size" else "constant")
        assert ("stroke" in entry) == (kind == "stroke")
        assert ("channels" in entry) == (kind == "style")
    finally:
        interaction._free_pyramid(trace)
