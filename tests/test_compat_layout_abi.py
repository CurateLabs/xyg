"""ABI 126 compatibility static-export layout combination."""

from __future__ import annotations

import math

import pytest

from xyg import _native, _svg


def test_compact_default_padding_matches_static_exporters() -> None:
    assert _native.compat_is_compact(519.0) is True
    assert _native.compat_is_compact(520.0) is False
    assert _native.compat_default_padding(True) == (6.0, 8.0, 36.0, 46.0)
    assert _native.compat_default_padding(False) == (10.0, 14.0, 42.0, 62.0)


def test_title_wrap_width_is_a_floor_of_forty() -> None:
    native = _native.compat_title_wrap_width(100.0, 40.0, 40.0)
    assert native == 40.0
    assert _svg._title_wrap_width(100.0, 40.0, 40.0) == pytest.approx(native)
    assert _native.compat_title_wrap_width(200.0, 46.0, 14.0) == 140.0


def test_colorbar_extra_and_right_y_room() -> None:
    assert _native.compat_colorbar_extra("figure_vertical", False, False) == (86.0, 0.0)
    assert _native.compat_colorbar_extra("axes_horizontal", True, False) == (0.0, 40.0)
    assert _native.compat_right_y_room(True) == 42.0
    assert _native.compat_right_y_room(False) == 54.0


def test_polar_legend_room_clamps_fraction() -> None:
    assert _native.polar_legend_room(400.0) == 120.0
    assert _native.polar_legend_room(1000.0) == 200.0
    mid = _native.polar_legend_room(700.0)
    assert mid == pytest.approx(math.floor(700.0 * 0.22))
    assert _svg._polar_legend_room(720.0) == pytest.approx(_native.polar_legend_room(720.0))


def test_polar_label_room_floor_without_authored_labels() -> None:
    assert _native.polar_label_room(None) == 30.0
    assert _svg._polar_label_room({}) == pytest.approx(30.0)


def test_recut_authored_padding_insets_by_label_room() -> None:
    plot = {"x": 0.0, "y": 0.0, "w": 200.0, "h": 200.0, "top_axis_room": 10.0}
    native = _native.recut_polar_plot(
        plot,
        200.0,
        200.0,
        polar_label_room=30.0,
        authored_padding=True,
    )
    assert native["x"] == 30.0
    assert native["y"] == 30.0
    assert native["w"] == 140.0
    assert native["h"] == 140.0
    assert native["top_axis_room"] == 40.0
    host = {
        "x": 0.0,
        "y": 0.0,
        "w": 200.0,
        "h": 200.0,
        "top_axis_room": 10.0,
    }
    _svg._recut_polar_plot(
        {"coords": "polar", "x_axis": {}, "y_axis": {}, "padding": [0.0, 0.0, 0.0, 0.0]},
        host,
        200.0,
        200.0,
        compact=False,
    )
    assert host["x"] == pytest.approx(native["x"])
    assert host["y"] == pytest.approx(native["y"])
    assert host["w"] == pytest.approx(native["w"])
    assert host["h"] == pytest.approx(native["h"])
    assert host["top_axis_room"] == pytest.approx(native["top_axis_room"])
