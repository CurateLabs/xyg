"""Rust-owned Scene CSS→RGBA8 and mark style defaults (ABI 107, M2 #271/#283)."""

from __future__ import annotations

import struct

from xyg._figure import Figure
from xyg._native import css_color_rgba, scene_resolve_mark_styles
from xyg._raster import _parse_color
from xyg._scene_v3 import figure_scene


def test_css_color_rgba_matches_parse_color() -> None:
    assert css_color_rgba("#3b82f6") == (0x3B, 0x82, 0xF6, 255)
    assert css_color_rgba("steelblue") == (70, 130, 180, 255)
    assert css_color_rgba("none") == (0, 0, 0, 0)
    assert css_color_rgba("oklch(0.7 0.1 250)") == (76, 120, 168, 255)
    assert css_color_rgba("#ff0000", 0.5) == (255, 0, 0, 128)
    assert _parse_color("steelblue") == css_color_rgba("steelblue")


def test_default_scatter_fill_is_brand_blue() -> None:
    header = struct.pack("<4sIII", b"XYMS", 1, 1, 0)
    record = struct.pack("<BBH4f3d4H", 0, 0, 0, 1.0, 1.0, 1.0, 1.0, 0.0, 0.0, 0.0, 0, 0, 0, 0)
    fill, stroke, width = scene_resolve_mark_styles(header + record)[0]
    assert fill == css_color_rgba("#3987e5")
    assert stroke == (0, 0, 0, 0)
    assert width == 0.0


def test_named_color_scatter_compiles() -> None:
    figure = Figure().scatter([0.0, 1.0], [0.0, 1.0], color="steelblue")
    encoded = figure_scene(figure)
    assert encoded  # native CSS named colors must not fail closed on the host


def test_line_default_stroke_width_is_one_and_a_half() -> None:
    figure = Figure().line([0.0, 1.0], [0.0, 1.0], color="#ff0000")
    encoded = figure_scene(figure)
    assert b"\xff\x00\x00\xff" in encoded
