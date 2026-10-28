"""ABI 396 canonical f64 drill localization: bounded output and honest refusal."""

from __future__ import annotations

import ctypes
import struct
from typing import Any

import numpy as np
import pytest

from xyg import _native, kernels


def query(x, y=None, window=(0.0, 1.0, 0.0, 1.0), *, chunk=65_536, in_drill=False):
    if y is None:
        y = x
    zx = kernels.zone_maps(x, chunk)
    zy = kernels.zone_maps(y, chunk)
    return kernels.canonical_drill_query(
        x, y, zx[0], zx[1], zy[0], zy[1], *window, chunk_size=chunk, in_drill=in_drill
    )


def test_f64_canonical_rows_endpoints_nulls_and_pruned_reads():
    x = np.array([1e12, 1e12 + 0.001, np.nan, 1e12 + 0.003, 2e12, np.inf])
    y = np.array([0.0, 1.0, 2.0, 3.0, 100.0, 101.0])
    result = query(x, y, (1e12, 1e12 + 0.003, 0.0, 3.0), chunk=2)
    np.testing.assert_array_equal(result["indices"], [0, 1, 3])
    assert result["status"] == "complete"
    assert result["count"] == 3
    assert result["candidate_rows"] == result["rows_read"] == 4
    assert result["candidate_chunks"] == 2
    assert result["read_bytes"] == 64
    assert result["point_cap"] == 200_000
    assert result["scan_row_budget"] == 80_000_000
    empty = query(x, y, (5e12, 6e12, 0.0, 3.0), chunk=2)
    assert empty["count"] == empty["rows_read"] == 0
    assert query(np.array([], dtype=np.float64))["count"] == 0
    assert query(np.full(10, np.nan))["count"] == 0


def test_entry_hysteresis_output_cap_and_overflow_never_certifies_prefix(monkeypatch):
    allocations = []
    original = np.empty

    def record(shape, *args, **kwargs):
        allocations.append(shape)
        return original(shape, *args, **kwargs)

    x = np.zeros(240_000)
    monkeypatch.setattr(_native.np, "empty", record)
    for in_drill in (False, True):
        limits = np.empty(2, dtype=np.uint64)
        assert _native._lib.xyg_canonical_drill_limits(in_drill, limits.ctypes.data) == 1
        cap = int(limits[0])
        assert kernels.drill_decision(cap, 200_000, in_drill)
        assert not kernels.drill_decision(cap + 1, 200_000, in_drill)
        complete = query(x[:cap], in_drill=in_drill)
        assert complete["count"] == cap
        assert complete["indices"][-1] == cap - 1
        refused = query(x, in_drill=in_drill)
        assert refused["status"] == "overflow"
        assert refused["count"] is None
        assert len(refused["indices"]) == 0
        assert refused["rows_read"] == cap + 1
    assert len(x) not in allocations
    assert max(shape for shape in allocations if isinstance(shape, int)) < len(x)


def test_scan_budget_preflight_memmap_borrows_pointers_and_reads_zero(tmp_path, monkeypatch):
    # Sparse zero-backed file, metadata-only refusal: no ingest and no scale timing.
    n = 80_000_001
    path = tmp_path / "canonical.f64"
    with path.open("wb") as file:
        file.truncate(n * 8)
    x = np.memmap(path, dtype=np.float64, mode="r", shape=(n,))
    chunks = (n + 65_535) // 65_536
    lo = np.zeros(chunks)
    hi = np.ones(chunks)
    original = _native._lib.xyg_canonical_drill_query
    pointers = []

    def record(x_pointer, y_pointer, *args):
        pointers.append((x_pointer, y_pointer))
        return original(x_pointer, y_pointer, *args)

    monkeypatch.setattr(_native._lib, "xyg_canonical_drill_query", record)
    result = kernels.canonical_drill_query(x, x, lo, hi, lo, hi, 0, 1, 0, 1)
    assert pointers == [(x.ctypes.data, x.ctypes.data)]
    assert result["status"] == "scan-budget"
    assert result["count"] is None
    assert len(result["indices"]) == 0
    assert result["candidate_rows"] == n
    assert result["candidate_chunks"] == chunks
    assert result["rows_read"] == result["read_bytes"] == 0
    assert not x.flags.writeable


def test_admission_estimate_is_not_a_count_and_refinement_is_rust_owned():
    estimate = kernels.canonical_drill_estimate(2_000_000, (0, 100, 0, 100), (0, 10, 0, 10))
    assert estimate == 20_000
    assert kernels.canonical_drill_admit(estimate)
    assert not kernels.canonical_drill_admit(2_000_000)
    assert kernels.canonical_drill_admit(2_000_000, refinement=True)
    assert not kernels.canonical_drill_admit(-1)
    assert kernels.canonical_drill_admit(-1, refinement=True)
    with pytest.raises(ValueError):
        kernels.canonical_drill_admit(np.nan)
    with pytest.raises(ValueError):
        kernels.canonical_drill_estimate(1, (0, 0, 0, 1), (0, 1, 0, 1))


def test_malformed_query_does_not_touch_output_or_stats():
    x = np.zeros(1)
    out = np.full(200_000, 42, dtype=np.uint32)
    stats = np.full(7, 77, dtype=np.uint64)
    status = _native._lib.xyg_canonical_drill_query(
        x.ctypes.data,
        x.ctypes.data,
        1,
        1,
        x.ctypes.data,
        x.ctypes.data,
        x.ctypes.data,
        x.ctypes.data,
        1,
        np.nan,
        1,
        0,
        1,
        0,
        out.ctypes.data,
        len(out),
        stats.ctypes.data,
    )
    assert status == -1
    assert np.all(out == 42)
    assert np.all(stats == 77)
    with pytest.raises(ValueError, match="contiguous f64"):
        query(np.zeros(10)[::2])
    with pytest.raises(ValueError):
        kernels.canonical_drill_query(x, x, x[:0], x[:0], x[:0], x[:0], 0, 1, 0, 1)


def test_xydc_validation_reuses_store_decoder_without_inventory_mutation():
    good = struct.pack("<4sIQdiI", b"XYDC", 1, 7, 0.5, 2, 1) + struct.pack("<III", 2, 1, 3)
    assert kernels.tile_paint_control_valid(good)
    assert kernels.tile_paint_control_valid(b"")
    assert not kernels.tile_paint_control_valid(good[:-1])
    assert not kernels.tile_paint_control_valid(b"bogus")
    assert not kernels.tile_paint_control_valid(
        struct.pack("<4sIQdiI", b"XYDC", 1, 7, np.nan, 2, 0)
    )
    invalid: Any = ctypes.c_void_p()
    assert not kernels.tile_paint_control_valid(invalid)
