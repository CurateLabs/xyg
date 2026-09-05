"""ABI 130 tick-label formatting: Python host wrappers match Rust goldens."""

from __future__ import annotations

import math

from xyg import _native
from xyg._layout import _fmt_axis, _fmt_log, _tick_text


def test_native_linear_log_time_and_number_spec() -> None:
    assert _native.tick_format(0.25, 0.25) == "0.25"
    assert _native.tick_format(1_234_567.8, 1.0) == "1.2e6"
    assert _native.tick_format(0.001, 1.0, scale="log") == "0.001"
    assert _native.tick_format(12_345.678, 1.0, format="$,.1f ms") == "$12,345.7 ms"
    assert _native.tick_format(0.125, 0.1, format=".1%") == "12.5%"
    assert _native.tick_format(0.0, 86_400_000.0, kind="time") == "Jan 01"
    assert _native.tick_format(0.0, 86_400_000.0, kind="time", format="%Y-%m-%d") == "1970-01-01"


def test_native_category_and_angular() -> None:
    assert _native.tick_format(1.0, 1.0, kind="category", categories=["a", "b", "c"]) == "b"
    assert _native.tick_format(math.pi / 2.0, 1.0, theta_unit="radians") == "π/2"
    assert _native.tick_format(22.5, 22.5, theta_unit="degrees") == "22.5°"
    assert _native.tick_format(90.0, 45.0, theta_unit="degrees", format=".0f deg") == "90 deg"


def test_svg_packer_matches_native() -> None:
    linear = {"kind": "linear", "range": [0.0, 10.0]}
    assert _fmt_axis(linear, 0.25, 0.25) == "0.25"
    log_axis = {"kind": "linear", "scale": "log", "range": [0.001, 1.0]}
    assert _fmt_axis(log_axis, 0.001, 1.0) == "0.001"
    time_axis = {"kind": "time", "range": [0.0, 86_400_000.0]}
    assert _fmt_axis(time_axis, 0.0, 86_400_000.0) == "Jan 01"
    category = {"kind": "category", "categories": ["x", "y", "z"]}
    assert _fmt_axis(category, 2.0, 1.0) == "z"
    assert _fmt_log(0.001) == "0.001"


def test_tick_text_authored_labels_win() -> None:
    axis = {
        "kind": "linear",
        "range": [0.0, 10.0],
        "tick_values": [0.0, 5.0, 10.0],
        "tick_labels": ["low", "mid", "high"],
    }
    assert _tick_text(axis, 5.0, 5.0) == "mid"
    assert _tick_text(axis, 3.0, 5.0) == "3"
