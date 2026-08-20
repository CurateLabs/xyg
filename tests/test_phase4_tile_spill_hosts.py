"""Phase-4 WP2: host tile-spill engagement (MB-scale fixtures)."""

from __future__ import annotations

import hashlib

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
