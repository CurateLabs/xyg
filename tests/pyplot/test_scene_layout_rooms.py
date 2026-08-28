"""Default-font cartesian Scene rooms and pyplot left gutters (#297)."""

from __future__ import annotations

import xyg.pyplot as plt
from xyg import _svg
from xyg.pyplot import _mplfig


def test_pyplot_default_font_left_gutter_uses_scene_plot_layout() -> None:
    fig, ax = plt.subplots(figsize=(3.2, 2.4), dpi=100)
    try:
        ax.scatter([1.0, 2.0], [1.0, 2.0])
        spec = _mplfig._probe_axis_spec(ax, 320, 240)
        intrinsic = dict(spec)
        intrinsic.pop("padding", None)
        rooms = _svg.scene_layout_rooms(intrinsic)
        assert rooms is not None
        layout_width, layout_height, _compact, plot = _svg.layout(intrinsic)
        # Pyplot get_position still composes `_svg.layout()` so frames agree.
        assert _mplfig._measured_axis_chrome(ax, 320, 240) == (
            float(plot["x"]),
            float(plot["y"]),
            float(layout_width - plot["x"] - plot["w"]),
            float(layout_height - plot["y"] - plot["h"]),
        )
        gutter_rooms = _svg.scene_layout_rooms(spec)
        assert gutter_rooms is not None
        assert _mplfig._measured_left_gutter(ax, 320, 240) == gutter_rooms[0]
    finally:
        plt.close(fig)
