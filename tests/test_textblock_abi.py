"""ABI 125 text-block measure and cartesian axis rooms."""

from __future__ import annotations

import pytest

from xyg import _native, _textblock
from xyg._svg import _x_axis_title_room, _y_axis_left_room


def test_text_block_measure_normalizes_crlf() -> None:
    native = _native.text_block_measure("first\r\nsecond", 12.0)
    packed = _textblock.measure("first\nsecond", 12.0)
    assert native["lines"] == ["first", "second"]
    assert packed.lines == tuple(native["lines"])
    assert packed.line_count == 2
    assert native["line_count"] == 2


def test_text_block_rotated_extent_swaps_at_ninety_degrees() -> None:
    width, height = _native.text_block_rotated_extent(10.0, 4.0, 90.0)
    assert width == pytest.approx(4.0)
    assert height == pytest.approx(10.0)
    block = _textblock.TextBlock(
        lines=("x",),
        width=10.0,
        height=4.0,
        line_step=4.0,
        ascent=3.0,
        descent=1.0,
    )
    assert _textblock.rotated_extent(block, 90.0) == (width, height)


def test_y_axis_left_room_titled_matches_host_gutter() -> None:
    native = _native.y_axis_left_room(7.0, 23.0, "Y", 12.0, 12.0 * 0.4)
    spec = {
        "x_axis": {},
        "y_axis": {
            "label": "Y",
            "side": "left",
            "range": [0.0, 1.0],
            "style": {"label_size": 12.0},
        },
    }
    host = _y_axis_left_room(spec, 300.0)
    title_only = _native.y_axis_left_room(0.0, 0.0, "Y", 12.0, 12.0 * 0.4)
    assert native > 23.0
    assert host > title_only
    assert _native.y_axis_left_room(0.0, 0.0, "", 12.0, 0.0) == 0.0


def test_x_axis_title_room_bottom_exceeds_historical_band() -> None:
    room = _native.x_axis_title_room("X", 12.0, 0.0, False)
    assert room > 24.0
    host = _x_axis_title_room({"label": "X", "side": "bottom", "style": {"label_size": 12}})
    assert host == pytest.approx(room)
