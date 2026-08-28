"""Default-font cartesian pyplot chrome uses Scene rooms (#297)."""

from __future__ import annotations

import xyg.pyplot as plt
from xyg import _svg
from xyg.pyplot import _mplfig


def test_pyplot_default_font_chrome_uses_scene_plot_layout() -> None:
    fig, ax = plt.subplots(figsize=(3.2, 2.4), dpi=100)
    try:
        ax.scatter([1.0, 2.0], [1.0, 2.0])
        left, top, right, bottom = _mplfig._measured_axis_chrome(ax, 320, 240)
        spec = _mplfig._probe_axis_spec(ax, 320, 240)
        intrinsic = dict(spec)
        intrinsic.pop("padding", None)
        rooms = _svg.scene_layout_rooms(intrinsic)
        assert rooms is not None
        assert (left, right, top, bottom) == rooms
        gutter_rooms = _svg.scene_layout_rooms(spec)
        assert gutter_rooms is not None
        assert _mplfig._measured_left_gutter(ax, 320, 240) == gutter_rooms[0]
    finally:
        plt.close(fig)
