"""Rust-owned Scene CSS, packing, chrome, legend, and colorbar (ABI 107–111)."""

from __future__ import annotations

import struct

import pytest

from xyg._figure import Figure
from xyg._native import (
    css_color_rgba,
    scene_pack_colorbar,
    scene_pack_legend,
    scene_pack_trace,
    scene_resolve_chrome_style,
    scene_resolve_mark_styles,
)
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


def test_default_chrome_style_matches_scene_defaults() -> None:
    header = struct.pack("<4sIIHH", b"XYCH", 1, 0, 0, 0)
    chrome = scene_resolve_chrome_style(header)
    assert len(chrome) == 200
    assert chrome[8:12] == bytes((32, 32, 32, 217))
    assert struct.unpack_from("<d", chrome, 16)[0] == 12.0
    assert chrome[24 + 12 : 24 + 16] == bytes((32, 32, 32, 36))
    assert chrome[24 + 16 : 24 + 20] == bytes((32, 32, 32, 140))


def test_grid_opacity_scales_default_grid_without_authored_color() -> None:
    from xyg import _scene_v3

    figure = Figure().scatter([0.0, 1.0], [0.0, 1.0])
    figure.set_axis("x", style={"grid_opacity": 0})
    chrome = _scene_v3._scene_chrome_style(figure)
    assert chrome[24 + 12 : 24 + 16] == bytes((32, 32, 32, 0))
    assert chrome[112 + 12 : 112 + 16] == bytes((32, 32, 32, 36))


def test_pack_trace_scatter_keeps_one_row_per_point() -> None:
    kinds, ids, refs, diameters, symbols, modes, coords = scene_pack_trace(
        0,
        [[0.0, 1.0], [2.0, 3.0]],
        symbol=4,
        style_ref=1,
        trace_id=7,
        diameter=6.0,
    )
    assert list(kinds) == [0, 0]
    assert list(ids) == [7, 7]
    assert list(refs) == [1, 1]
    assert list(symbols) == [4, 4]
    assert list(modes) == [0, 0]
    assert list(diameters) == [6.0, 6.0]
    assert coords[0].tolist() == [0.0, 1.0]
    assert coords[1].tolist() == [2.0, 3.0]


def test_pack_trace_heatmap_frames_extent_then_shape() -> None:
    kinds, ids, refs, diameters, symbols, modes, coords = scene_pack_trace(
        7,
        [[1.0], [2.0], [3.0], [4.0]],
        style_ref=9,
        trace_id=11,
        extra0=2.0,
        extra1=3.0,
    )
    assert list(kinds) == [2, 2]
    assert list(ids) == [11, 11]
    assert list(diameters) == [2.0, 3.0]
    assert list(modes) == [6, 6]
    assert coords[0].tolist() == [1.0, 0.0]
    assert coords[1].tolist() == [2.0, 0.0]
    assert coords[2].tolist() == [3.0, 0.0]
    assert coords[3].tolist() == [4.0, 0.0]


def test_pack_trace_rejects_nonfinite_coordinates() -> None:
    with pytest.raises(ValueError, match="missing-data"):
        scene_pack_trace(1, [[0.0, float("nan")], [1.0, 2.0]])


def test_pack_legend_frames_xylg_header_and_label() -> None:
    framed = scene_pack_legend(
        loc=1,
        flags=1 | (1 << 3),
        font_size=0.0,
        title_font_size=0.0,
        text_rgba=bytes((32, 32, 32, 255)),
        frame_fill_rgba=bytes(4),
        title=b"",
        entry_meta=struct.pack("<IBB2x4s4s", 1, 0, 3, bytes((0x39, 0x87, 0xE5, 255)), bytes(4)),
        label_lens=[6],
        labels=b"series",
    )
    assert framed[:4] == b"XYLG"
    assert framed[4] == 1
    assert framed[5] == 1 | (1 << 3)
    assert framed[32:36] == bytes((32, 32, 32, 255))
    assert framed[48:52] == (1).to_bytes(4, "little")
    assert framed[-6:] == b"series"


def test_named_scatter_legend_compiles_through_rust_xylg() -> None:
    figure = Figure().scatter([0.0, 1.0], [0.0, 1.0], name="series")
    encoded = figure_scene(figure)
    assert b"XYLG" in encoded
    assert b"series" in encoded


def test_pack_colorbar_frames_v2_header_stops_and_ticks() -> None:
    framed = scene_pack_colorbar(
        flags=1 << 2,
        lo=0.0,
        hi=1.0,
        text_rgba=bytes((32, 32, 32, 255)),
        title=b"",
        stop_values=[0.0, 1.0],
        stop_rgba=bytes((0, 0, 0, 255, 255, 255, 255, 255)),
        ticks=[0.0, 0.5, 1.0],
    )
    assert framed[:4] == b"XYCB"
    assert int.from_bytes(framed[4:8], "little") == 2
    assert framed[8] == 0b1110
    assert int.from_bytes(framed[16:20], "little") == 3
    ticks_at = 56 + 2 * 12
    assert struct.unpack_from("<d", framed, ticks_at)[0] == 0.0
    assert struct.unpack_from("<d", framed, ticks_at + 8)[0] == 0.5
    assert struct.unpack_from("<d", framed, ticks_at + 16)[0] == 1.0


def test_pack_colorbar_rejects_stops_that_miss_the_domain() -> None:
    with pytest.raises(ValueError, match="strictly increasing"):
        scene_pack_colorbar(
            flags=0,
            lo=0.0,
            hi=1.0,
            text_rgba=bytes((32, 32, 32, 255)),
            title=b"",
            stop_values=[0.1, 1.0],
            stop_rgba=bytes((0, 0, 0, 255, 255, 255, 255, 255)),
            ticks=[],
        )
