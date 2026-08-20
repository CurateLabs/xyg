"""Canonical i64 temporal columns and interval indexes (#43)."""

from __future__ import annotations

import numpy as np
import pytest

from xyg import _native

SUB_MS_MICROS = 1_704_067_200_000_123


def test_exact_timestamp_survives_python_roundtrip() -> None:
    handle = _native.temporal_column_create(
        [SUB_MS_MICROS],
        [1],
        timezone="UTC",
        unit=_native.TEMPORAL_PRECISION_MICROSECOND,
    )
    try:
        values, validity, timezone, precision = _native.temporal_column_read(handle)
        assert values.dtype == np.int64
        assert values.tolist() == [SUB_MS_MICROS]
        assert validity.tolist() == [1]
        assert timezone == "UTC"
        assert precision == _native.TEMPORAL_PRECISION_MICROSECOND
    finally:
        _native.temporal_column_destroy(handle)


def test_millisecond_unit_normalizes_to_micros() -> None:
    handle = _native.temporal_column_create(
        [1_704_067_200_000],
        [1],
        timezone="America/New_York",
        unit=_native.TEMPORAL_PRECISION_MILLISECOND,
    )
    try:
        values, _, timezone, precision = _native.temporal_column_read(handle)
        assert values.tolist() == [1_704_067_200_000_000]
        assert timezone == "America/New_York"
        assert precision == _native.TEMPORAL_PRECISION_MILLISECOND
    finally:
        _native.temporal_column_destroy(handle)


def test_pre_epoch_and_nulls() -> None:
    handle = _native.temporal_column_create(
        [-1_000_000, 0],
        [1, 0],
        timezone="UTC",
    )
    try:
        values, validity, _, _ = _native.temporal_column_read(handle)
        assert values.tolist() == [-1_000_000, 0]
        assert validity.tolist() == [1, 0]
    finally:
        _native.temporal_column_destroy(handle)


def test_dst_gap_and_fold_outcomes() -> None:
    with pytest.raises(_native.TemporalNativeError) as gap:
        _native.temporal_column_create(
            [0],
            [1],
            timezone="America/New_York",
            naive=True,
            dst_status=[_native.TEMPORAL_DST_GAP],
            offset_seconds=[0],
            fold_later_offset_seconds=[0],
        )
    assert gap.value.status == -5

    with pytest.raises(_native.TemporalNativeError) as fold:
        _native.temporal_column_create(
            [0],
            [1],
            timezone="America/New_York",
            naive=True,
            disambiguation=_native.TEMPORAL_DISAMBIGUATION_REJECT,
            dst_status=[_native.TEMPORAL_DST_FOLD],
            offset_seconds=[-14400],
            fold_later_offset_seconds=[-18000],
        )
    assert fold.value.status == -6

    handle = _native.temporal_column_create(
        [3_600_000_000],
        [1],
        timezone="America/New_York",
        naive=True,
        disambiguation=_native.TEMPORAL_DISAMBIGUATION_PREFER_EARLIER,
        dst_status=[_native.TEMPORAL_DST_FOLD],
        offset_seconds=[-14400],
        fold_later_offset_seconds=[-18000],
    )
    try:
        values, _, _, _ = _native.temporal_column_read(handle)
        assert values.tolist() == [3_600_000_000 + 14_400_000_000]
    finally:
        _native.temporal_column_destroy(handle)


def test_interval_boundaries_are_end_exclusive() -> None:
    handle = _native.temporal_interval_index_create(
        starts=[10, 0, 50],
        start_valid=[1, 0, 1],
        ends=[20, 40, 0],
        end_valid=[1, 1, 0],
    )
    try:
        assert _native.temporal_interval_visibility_at(handle, 10).tolist() == [1, 1, 0]
        assert _native.temporal_interval_visibility_at(handle, 20).tolist() == [0, 1, 0]
        assert _native.temporal_interval_visibility_at(handle, 50).tolist() == [0, 0, 1]
    finally:
        _native.temporal_interval_index_destroy(handle)


def test_reversed_interval_fails_before_output() -> None:
    with pytest.raises(_native.TemporalNativeError) as exc:
        _native.temporal_interval_index_create(
            starts=[5],
            start_valid=[1],
            ends=[5],
            end_valid=[1],
        )
    assert exc.value.status == -7


def test_events_in_range_half_open() -> None:
    visible = _native.temporal_events_in_range(
        [10, 20, 30],
        [1, 1, 1],
        range_start=10,
        range_end=30,
    )
    assert visible.tolist() == [1, 1, 0]


def test_timezone_required() -> None:
    with pytest.raises(ValueError, match="timezone"):
        _native.temporal_column_create([0], [1], timezone="")
