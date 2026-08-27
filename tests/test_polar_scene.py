"""Scene v26 polar compile: line/scatter/area/bar/column/errorbar/heatmap through Rust Scene."""

from __future__ import annotations

import math
import struct

import pytest

from xyg import _native
from xyg._figure import Figure
from xyg._scene_v3 import UnsupportedSceneV3, figure_scene, public_static_export


def test_polar_scatter_figure_scene_succeeds_version_26() -> None:
    figure = Figure(width=400, height=400, coords="polar")
    figure.scatter([0.0], [1.0], color="#3987e5", size=8)
    scene = figure_scene(figure)
    assert scene[:4] == b"XYGS"
    assert scene[4:8] == (26).to_bytes(4, "little")
    assert scene[-92:-88] == b"XYPL"


def test_polar_theta_zero_east_projects_to_cx_plus_r() -> None:
    figure = Figure(width=400, height=400, coords="polar")
    figure.axis_options["y"]["domain"] = (0.0, 1.0)
    figure.scatter([0.0], [1.0], color="#3987e5", size=8)
    scene = figure_scene(figure)
    left, top, right, bottom = struct.unpack_from("<dddd", scene, 48)
    styles = struct.unpack_from("<Q", scene, 24)[0]
    at = 160 + styles * 16
    x, y = struct.unpack_from("<dd", scene, at + 16)
    cx = (left + right) / 2.0
    cy = (top + bottom) / 2.0
    radius = min(right - left, bottom - top) / 2.0
    assert abs(x - (cx + radius)) < 1.0
    assert abs(y - cy) < 1.0


def test_polar_svg_has_ring_spoke_not_cartesian_x_grid() -> None:
    figure = Figure(width=400, height=400, coords="polar")
    figure.scatter([0.0, math.pi / 2], [0.5, 1.0], color="#3987e5", size=8)
    svg = _native.scene_svg(figure_scene(figure))
    assert 'data-xy-grid="ring"' in svg or 'data-xy-frame="polar"' in svg
    assert '<clipPath id="xy-scene-plot"><rect' not in svg
    public = public_static_export(figure, "svg")
    assert public is not None
    assert b'data-xy-grid="ring"' in public or b"circle" in public


def test_polar_line_and_area_are_scene_eligible() -> None:
    line = Figure(width=400, height=400, coords="polar")
    line.line([0.0, math.pi / 2], [0.5, 1.0], color="#3987e5")
    line_scene = figure_scene(line)
    assert line_scene[4:8] == (26).to_bytes(4, "little")
    assert line_scene[-92:-88] == b"XYPL"
    area = Figure(width=400, height=400, coords="polar")
    area.area([0.0, math.pi / 2, math.pi], [0.4, 0.8, 0.6], color="#22c55e")
    area_scene = figure_scene(area)
    assert area_scene[4:8] == (26).to_bytes(4, "little")
    svg = _native.scene_svg(area_scene)
    assert 'data-xy-grid="ring"' in svg or 'data-xy-frame="polar"' in svg


def test_polar_bar_and_column_are_scene_eligible() -> None:
    figure = Figure(width=400, height=400, coords="polar")
    figure.axis_options["x"]["domain"] = (0.0, 2.0)
    figure.axis_options["y"]["domain"] = (0.0, 1.0)
    figure.bar([0.0, 1.0], [0.5, 0.8], color="#3987e5")
    scene = figure_scene(figure)
    assert scene[:4] == b"XYGS"
    assert scene[4:8] == (26).to_bytes(4, "little")
    assert scene[-92:-88] == b"XYPL"
    svg = _native.scene_svg(scene)
    assert "<path" in svg and 'd="M' in svg
    assert 'data-xy-grid="ring"' in svg or 'data-xy-frame="polar"' in svg
    assert "<rect x=" not in svg
    public_svg = public_static_export(figure, "svg")
    assert public_svg is not None
    assert b"<path" in public_svg
    public_png = public_static_export(figure, "png")
    assert public_png is not None
    column = Figure(width=400, height=400, coords="polar")
    column.axis_options["x"]["domain"] = (0.0, math.pi)
    column.axis_options["y"]["domain"] = (0.0, 1.0)
    column.column([0.0, math.pi / 2], [0.4, 0.9], color="#22c55e")
    column_scene = figure_scene(column)
    assert column_scene[4:8] == (26).to_bytes(4, "little")
    column_svg = _native.scene_svg(column_scene)
    assert "<path" in column_svg and 'd="M' in column_svg
    assert "<rect x=" not in column_svg


def test_polar_errorbar_is_scene_eligible() -> None:
    figure = Figure(width=400, height=400, coords="polar")
    figure.axis_options["x"]["domain"] = (0.0, math.pi)
    figure.axis_options["y"]["domain"] = (0.0, 1.0)
    figure.errorbar([0.0, math.pi / 2], [0.5, 0.8], yerr=0.1, cap_size=0.0, color="#3987e5")
    scene = figure_scene(figure)
    assert scene[4:8] == (26).to_bytes(4, "little")
    svg = _native.scene_svg(scene)
    assert "<path" in svg or "<line" in svg
    assert public_static_export(figure, "svg") is not None


def test_polar_heatmap_is_scene_eligible() -> None:
    figure = Figure(width=400, height=400, coords="polar")
    figure.axis_options["x"]["domain"] = (0.0, 2.0)
    figure.axis_options["y"]["domain"] = (0.0, 2.0)
    figure.heatmap([[1.0, 2.0], [3.0, 4.0]])
    scene = figure_scene(figure)
    assert scene[:4] == b"XYGS"
    assert scene[4:8] == (26).to_bytes(4, "little")
    assert scene[-92:-88] == b"XYPL"
    svg = _native.scene_svg(scene)
    assert "<path" in svg and 'd="M' in svg
    assert "<rect x=" not in svg
    assert 'data-xy-grid="ring"' in svg or 'data-xy-frame="polar"' in svg
    public_svg = public_static_export(figure, "svg")
    assert public_svg is not None
    assert b"<path" in public_svg
    public_png = public_static_export(figure, "png")
    assert public_png is not None


def test_polar_density_still_unsupported() -> None:
    figure = Figure(width=400, height=400, coords="polar")
    figure.scatter([0.0, math.pi / 2], [0.5, 1.0], density=True, color="#3987e5")
    with pytest.raises(UnsupportedSceneV3, match="density"):
        figure_scene(figure)


def test_polar_contour_still_unsupported() -> None:
    figure = Figure(width=400, height=400, coords="polar")
    figure.contour([[1.0, 2.0], [3.0, 4.0]], levels=2, color="#3987e5")
    with pytest.raises(UnsupportedSceneV3, match="XYG_SCENE_UNSUPPORTED_POLAR"):
        figure_scene(figure)


def test_cartesian_hidden_chrome_is_not_inferred_as_polar() -> None:
    figure = Figure(width=200, height=120)
    figure.scatter([0.0, 1.0], [0.0, 1.0], color="#3987e5")
    for axis in ("x", "y"):
        figure.axis_options[axis]["style"] = {
            "axis_width": 0,
            "tick_width": 0,
            "tick_length": 0,
            "grid_width": 0,
            "axis_color": "#00000000",
            "grid_color": "#00000000",
            "tick_color": "#00000000",
            "tick_label_color": "#00000000",
            "label_color": "#00000000",
        }
    scene = figure_scene(figure)
    assert scene[4:8] == (26).to_bytes(4, "little")
    assert scene[-4:] != b"XYPL"
    svg = _native.scene_svg(scene)
    assert 'data-xy-grid="ring"' not in svg
    assert 'data-xy-frame="polar"' not in svg
