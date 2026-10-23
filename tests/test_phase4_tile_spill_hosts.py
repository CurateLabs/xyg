"""Phase-4 WP2: host tile-spill engagement (MB-scale fixtures)."""

from __future__ import annotations

import hashlib
import struct

import numpy as np
import pytest

import xyg
from xyg import kernels
from xyg.config import DENSITY_GRID, PYRAMID_MIN_POINTS, PYRAMID_RESIDENT_BYTES
from xyg.interaction import (
    _ensure_pyramid,
    _pyramid_resident_bytes,
    _tile_store_of,
    _wants_pyramid_spill,
    pyramid_report_bytes,
    pyramid_spilled_bytes,
    sync_tile_budget,
)


@pytest.fixture(autouse=True)
def _restore_tile_budget():
    sync_tile_budget(PYRAMID_RESIDENT_BYTES)
    yield
    sync_tile_budget(PYRAMID_RESIDENT_BYTES)


def _scatter_points(n: int, seed: int = 0) -> tuple[np.ndarray, np.ndarray]:
    rng = np.random.default_rng(seed)
    return rng.random(n), rng.random(n)


def test_pyramid_spill_bindings_compose_bit_identical_to_ram():
    n = 8_192
    x = np.fromiter((((i * 17) % n) / n for i in range(n)), dtype=np.float64, count=n)
    y = np.fromiter((((i * 31) % n) / n for i in range(n)), dtype=np.float64, count=n)
    handle = kernels.pyramid_build(x, y, 0.0, 1.0, 0.0, 1.0, 128)
    assert handle
    ram = kernels.pyramid_compose(handle, 0.0, 1.0, 0.0, 1.0, 64, 48, max_upsample=16)
    assert ram is not None
    store = kernels.pyramid_spill(handle)
    assert store
    assert kernels.pyramid_free(handle)
    tiles = kernels.tile_store_compose(store, 0.0, 1.0, 0.0, 1.0, 64, 48, max_upsample=16)
    assert tiles is not None
    np.testing.assert_array_equal(ram[0], tiles[0])
    assert ram[1] == tiles[1]
    assert hashlib.sha256(tiles[0].astype("<f4", copy=False).tobytes()).hexdigest() == (
        "e8e9e65493798cfeecd8e1e1ecee19a9e2a786121f8f8051a9bbc114515c3b2b"
    )
    stats = kernels.tile_store_stats(store)
    assert stats is not None
    hit, miss, resident, spilled, budget, over = stats
    assert hit + miss >= 1
    assert spilled > 0
    assert budget == PYRAMID_RESIDENT_BYTES
    assert over is False or resident >= budget
    assert kernels.tile_store_free(store)


def test_ensure_pyramid_force_spill_records_tiles_on_density_view():
    n = PYRAMID_MIN_POINTS
    x, y = _scatter_points(n, seed=1)
    fig = xyg.scatter_chart(
        xyg.scatter(x, y, density=True, pyramid_spill=True), width=320, height=240
    ).figure()
    t = fig.traces[0]
    assert t.pyramid_spill is True
    handle = _ensure_pyramid(t)
    assert handle is None
    store = _tile_store_of(t)
    assert store
    update, _bufs = fig.density_view(t.id, 0.0, 1.0, 0.0, 1.0, 128, 96)
    entry = update["traces"][0]
    assert entry["binning"].startswith("pyramid-L")
    assert "-tiles" in entry["binning"]
    assert "tiles" in entry
    assert set(entry["tiles"]) >= {
        "hit",
        "miss",
        "resident_bytes",
        "spilled_bytes",
        "budget_bytes",
        "over_budget",
    }
    assert pyramid_spilled_bytes(fig) > 0
    assert pyramid_report_bytes(fig) == entry["tiles"]["resident_bytes"]


def test_spill_when_resident_would_exceed_budget(monkeypatch):
    from xyg import interaction

    tiny = 1024
    monkeypatch.setattr(interaction, "PYRAMID_RESIDENT_BYTES", tiny)
    sync_tile_budget(tiny)
    n = 4_096
    x, y = _scatter_points(n)
    fig = xyg.scatter_chart(xyg.scatter(x, y, density=True), width=320, height=240).figure()
    t = fig.traces[0]
    monkeypatch.setattr(interaction, "PYRAMID_MIN_POINTS", 1)
    t.pyramid_spill = False
    assert not _wants_pyramid_spill(t, 256, colored=False)
    t.pyramid_spill = True
    assert _wants_pyramid_spill(t, 256, colored=False)
    t.pyramid_spill = False
    monkeypatch.setattr(interaction, "PYRAMID_NO_RESCAN_ROWS", n - 1)
    base = 512
    assert _pyramid_resident_bytes(base, colored=False) > tiny
    assert _wants_pyramid_spill(t, base, colored=False)


def test_spill_configuration_rejects_ambiguous_values_before_ingest():
    with pytest.raises(ValueError, match="pyramid_spill"):
        xyg.scatter_chart(xyg.scatter([0.0], [0.0], pyramid_spill=1)).figure()
    with pytest.raises(ValueError, match="tile budget bytes"):
        sync_tile_budget(-1)


def test_explicit_spill_failure_is_actionable_and_releases_ram_cache(monkeypatch):
    from xyg import interaction

    x, y = _scatter_points(4_096, seed=3)
    fig = xyg.scatter_chart(
        xyg.scatter(x, y, density=True, pyramid_spill=True), width=320, height=240
    ).figure()
    trace = fig.traces[0]
    monkeypatch.setattr(interaction, "PYRAMID_MIN_POINTS", 1)
    monkeypatch.setattr(kernels, "pyramid_spill", lambda _handle: 0)
    with pytest.raises(RuntimeError, match="temporary-directory space and permissions"):
        _ensure_pyramid(trace)
    assert trace._pyr_handle is None
    assert trace._tile_store is None


def test_first_paint_records_tiles_binning():
    n = PYRAMID_MIN_POINTS
    x, y = _scatter_points(n, seed=2)
    fig = xyg.scatter_chart(
        xyg.scatter(x, y, density=True, pyramid_spill=True), width=320, height=240
    ).figure()
    spec, _blob = fig.build_payload()
    dens = spec["traces"][0]["density"]
    assert dens["binning"].startswith("pyramid-L")
    assert "-tiles" in dens["binning"]
    assert dens["reduction"] == "pyramid-count"
    assert "tiles" in dens
    assert dens["w"] * dens["h"] == DENSITY_GRID[0] * DENSITY_GRID[1]


def _small_colored_spill(monkeypatch, *, categorical=True):
    """Exercise the real host path with MB-scale grids, never a 1B-row fixture."""
    from xyg import interaction

    monkeypatch.setattr(interaction, "PYRAMID_MIN_POINTS", 1)
    monkeypatch.setattr(interaction, "PYRAMID_BASE_DIM", 512)
    monkeypatch.setattr(interaction, "SCATTER_DENSITY_THRESHOLD", 32)
    x, y = _scatter_points(32_768, seed=13)
    categories = np.where(x < 0.5, "left", "right")
    fig = xyg.scatter_chart(
        xyg.scatter(
            x, y, color=categories if categorical else x.copy(), density=True, pyramid_spill=True
        )
    ).figure()
    trace = fig.traces[0]
    assert _ensure_pyramid(trace) is None
    assert _tile_store_of(trace)
    return fig, trace


def test_spilled_legend_predicate_bypasses_tiles_and_restores_original_store(monkeypatch):
    from xyg import channels

    fig, trace = _small_colored_spill(monkeypatch)
    store = _tile_store_of(trace)
    control = struct.pack("<4sIQdiI", b"XYDC", 1, 0, -1.0, -1, 0)
    try:
        initial, _ = fig.density_view(trace.id, 0, 1, 0, 1, 128, 96, tile_cache=control)
        assert "tile_frame" in initial["traces"][0]["density"]
        before = kernels.tile_store_stats(store)
        for category in (0, 1):
            fig.legend_toggle(trace.id, True, category=category)
            update, buffers = fig.density_view(trace.id, 0, 1, 0, 1, 128, 96, tile_cache=control)
            entry = update["traces"][0]
            assert entry["binning"].endswith("-masked")
            assert "tiles" not in entry and "tile_frame" not in entry["density"]
            visible = trace.color_ch.codes != category
            assert entry["visible"] == int(visible.sum())
            density = entry["density"]
            rgba = np.frombuffer(buffers[density["rgba"]], dtype=np.uint8).reshape(-1, 4)
            palette = channels.palette_rgba8(trace.color_ch.palette, 2)
            lit = rgba[:, 3] > 0
            assert lit.any()
            np.testing.assert_array_equal(
                rgba[lit, :3], np.broadcast_to(palette[1 - category, :3], (lit.sum(), 3))
            )
            assert kernels.tile_store_stats(store)[:2] == before[:2]
            fig.legend_toggle(trace.id, False, category=category)
        restored, _ = fig.density_view(trace.id, 0, 1, 0, 1, 128, 96, tile_cache=control)
        assert "tile_frame" in restored["traces"][0]["density"]
        assert _tile_store_of(trace) == store
        assert kernels.tile_store_stats(store)[0] > before[0]
    finally:
        kernels.tile_store_free(store)
        trace._tile_store = None


def test_colored_spill_append_refuses_then_host_rebuilds(monkeypatch):
    fig, trace = _small_colored_spill(monkeypatch, categorical=False)
    old = _tile_store_of(trace)
    tail = np.array([0.25], dtype=np.float64)
    try:
        before = kernels.tile_store_compose_color(old, 0, 1, 0, 1, 64, 48, 16)
        assert before is not None
        assert kernels.tile_store_append(old, tail, tail) is False
        after = kernels.tile_store_compose_color(old, 0, 1, 0, 1, 64, 48, 16)
        assert after is not None
        np.testing.assert_array_equal(after[0], before[0])
        np.testing.assert_array_equal(after[1], before[1])
        fig.append(trace.id, tail, tail, color=[0.25])
        assert kernels.tile_store_stats(old) is None
        assert trace._tile_store is None
        assert _ensure_pyramid(trace) is None
        rebuilt = _tile_store_of(trace)
        assert rebuilt and rebuilt != old
        # A from-scratch public chart is the count/color oracle after append.
        fresh = (
            xyg.scatter_chart(
                xyg.scatter(
                    trace.x.values,
                    trace.y.values,
                    color=trace.color_ch.values,
                    density=True,
                    pyramid_spill=True,
                )
            )
            .figure()
            .traces[0]
        )
        try:
            _ensure_pyramid(fresh)
            actual = kernels.tile_store_compose_color(rebuilt, 0, 1, 0, 1, 64, 48, 16)
            expected = kernels.tile_store_compose_color(
                _tile_store_of(fresh), 0, 1, 0, 1, 64, 48, 16
            )
            assert actual is not None and expected is not None
            np.testing.assert_array_equal(actual[0], expected[0])
            np.testing.assert_array_equal(actual[1], expected[1])
        finally:
            if _tile_store_of(fresh):
                kernels.tile_store_free(fresh._tile_store)
                fresh._tile_store = None
    finally:
        if _tile_store_of(trace):
            kernels.tile_store_free(trace._tile_store)
            trace._tile_store = None


def test_two_host_stores_share_budget_and_release_residency():
    x, y = _scatter_points(4_096, seed=17)
    stores = []
    try:
        for _ in range(2):
            handle = kernels.pyramid_build(x, y, 0, 1, 0, 1, 512)
            try:
                stores.append(kernels.pyramid_spill(handle))
                assert stores[-1]
            finally:
                kernels.pyramid_free(handle)
        assert kernels.tile_budget_set(300_000)  # one count tile, not two
        for store in (stores[0], stores[1], stores[0]):
            assert kernels.tile_store_compose(store, 0, 1, 0, 1, 64, 48, 16) is not None
            assert kernels.tile_store_stats(store)[2] <= 300_000
        assert kernels.tile_store_stats(stores[0])[1] == 2  # sibling evicted its first tile
        assert kernels.tile_store_free(stores.pop())
        assert kernels.tile_store_free(stores.pop())
    finally:
        for store in stores:
            kernels.tile_store_free(store)


def test_colored_spill_cross_host_golden():
    """Same source, palette, dimensions and hash as the Node refusal fixture."""
    n = 8_192
    i = np.arange(n, dtype=np.float64)
    x, y = (i * 17 % n) / n, (i * 31 % n) / n
    idx = (x >= 0.5).astype(np.uint8)
    lut = np.array([[240, 30, 20, 255], [20, 60, 230, 255]], dtype=np.uint8)
    handle = kernels.pyramid_build_color(x, y, 0, 1, 0, 1, 512, idx=idx, lut=lut)
    store = 0
    try:
        store = kernels.pyramid_spill(handle)
        counts, rgba, level = kernels.tile_store_compose_color(store, 0, 1, 0, 1, 64, 48, 16)
        assert level == 3
        assert hashlib.sha256(counts.astype("<f4").tobytes() + rgba.tobytes()).hexdigest() == (
            "281ddd659661acc5873e9cb71c96b323fe15c8a96623592ad8bdd5763e6c51a4"
        )
    finally:
        if store:
            kernels.tile_store_free(store)
        kernels.pyramid_free(handle)
