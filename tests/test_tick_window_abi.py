"""ABI 128 authored tick-window: Python host wrappers match the Rust goldens."""

from __future__ import annotations

import math

from xyg import _native
from xyg._layout import _tick_window, _tick_window_filter, axis_ticks, minor_axis_ticks


def test_native_seam_crossing_degree_sector() -> None:
    lo, hi = _native.tick_window(
        0.0,
        360.0,
        theta_unit="degrees",
        sector_lo=300.0,
        sector_hi=420.0,
    )
    assert (lo, hi) == (300.0, 420.0)
    kept = _native.tick_window_filter(
        [300.0, 330.0, 0.0, 30.0, 60.0, 200.0],
        lo,
        hi,
        theta_unit="degrees",
    )
    assert kept == [300.0, 330.0, 0.0, 30.0, 60.0]


def test_native_linear_window_rejects_outside_and_nan() -> None:
    kept = _native.tick_window_filter(
        [0.0, 45.0, 90.0, 200.0, -10.0, float("nan")],
        0.0,
        180.0,
    )
    assert kept == [0.0, 45.0, 90.0]


def test_native_category_theta_window_uses_index_span() -> None:
    assert _native.tick_window(
        1.0,
        2.0,
        theta_unit="degrees",
        kind="category",
        n_categories=4,
    ) == (0.0, 3.0)


def test_svg_packer_matches_native_seam_crossing_ticks() -> None:
    axis = {
        "kind": "linear",
        "range": [0.0, 360.0],
        "theta_unit": "degrees",
        "sector": (300.0, 420.0),
        "tick_values": [300.0, 330.0, 0.0, 30.0, 60.0, 200.0],
        "minor_tick_values": [300.0, 15.0, 200.0, float("nan")],
    }
    assert _tick_window(axis) == (300.0, 420.0)
    ticks, labeled, _step = axis_ticks(axis, 400.0, True)
    assert ticks == labeled == [300.0, 330.0, 0.0, 30.0, 60.0]
    assert _tick_window_filter(axis, 300.0, 420.0, axis["tick_values"]) == ticks
    assert minor_axis_ticks(axis) == [300.0, 15.0]


def test_svg_packer_matches_native_linear_and_category() -> None:
    linear = {"kind": "linear", "range": [0.0, 180.0]}
    assert _tick_window(linear) == (0.0, 180.0)
    ticks, labeled, _step = axis_ticks(
        {**linear, "tick_values": [0.0, 45.0, 90.0, 200.0, -10.0, float("nan")]},
        400.0,
        True,
    )
    assert ticks == labeled == [0.0, 45.0, 90.0]
    category = {
        "kind": "category",
        "range": [1.0, 2.0],
        "theta_unit": "radians",
        "categories": ["a", "b", "c", "d"],
    }
    assert _tick_window(category) == (0.0, 3.0)
    assert _native.tick_window(0.0, math.pi, theta_unit="radians") == (0.0, math.pi)
    assert _native.tick_window(0.0, 1.0, theta_unit="degrees") == (0.0, 1.0)
