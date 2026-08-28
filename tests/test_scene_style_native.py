"""Rust-owned Scene CSS, packing, chrome, legend, colorbar, and annotations (ABI 107–112, 116)."""

from __future__ import annotations

import struct

import pytest

from xyg._figure import Figure
from xyg._native import (
    css_color_rgba,
    scene_pack_annotation_facts,
    scene_pack_annotation_marks,
    scene_pack_annotations,
    scene_pack_colorbar,
    scene_pack_density_grid,
    scene_pack_figure_chrome,
    scene_pack_heatmap_facts,
    scene_pack_legend,
    scene_pack_product,
    scene_pack_product_facts,
    scene_pack_public_export,
    scene_pack_scene_extras,
    scene_pack_trace,
    scene_pack_trace_compile,
    scene_resolve_chrome_style,
    scene_resolve_mark_styles,
    scene_resolve_pack_kind,
)
from xyg._raster import _parse_color
from xyg._scene_v3 import UnsupportedSceneV3, figure_scene


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


def test_empty_trace_compile_facts_emit_xyto() -> None:
    packed = scene_pack_trace_compile(
        b"XYTC" + (1).to_bytes(4, "little") + (0).to_bytes(8, "little")
    )
    assert packed[:4] == b"XYTO"
    assert int.from_bytes(packed[8:12], "little") == 0


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


def test_pack_product_matches_pack_trace_for_scatter() -> None:
    assert scene_resolve_pack_kind("scatter") == 0
    assert scene_resolve_pack_kind("heatmap", 2) == 9
    kinds, ids, refs, diameters, symbols, modes, coords = scene_pack_product(
        "scatter",
        [[0.0, 1.0], [2.0, 3.0], None, None, None, None, None],
        symbol=4,
        style_ref=1,
        trace_id=7,
        diameter=6.0,
    )
    assert list(kinds) == [0, 0]
    assert list(ids) == [7, 7]
    assert list(symbols) == [4, 4]
    assert list(diameters) == [6.0, 6.0]
    assert coords[0].tolist() == [0.0, 1.0]
    assert coords[1].tolist() == [2.0, 3.0]


def _xypk(
    kind: str,
    *,
    style_ref: int = 0,
    coords: int = 0,
    symbol: int = 0,
    step: int = 0,
    facts: int = 0,
    trace_id: int = 0,
    diameter: float = 0.0,
    hex_dx: float = 0.0,
    hex_dy: float = 0.0,
    grid_rows: float = 0.0,
    grid_cols: float = 0.0,
) -> bytes:
    return struct.pack(
        "<4sIIBBBBQddddd",
        b"XYPK",
        1,
        style_ref,
        coords,
        symbol,
        step,
        facts,
        trace_id,
        diameter,
        hex_dx,
        hex_dy,
        grid_rows,
        grid_cols,
    ) + kind.encode("utf-8")


def test_pack_product_facts_applies_cartesian_smooth_line() -> None:
    kinds, ids, refs, diameters, symbols, modes, coords = scene_pack_product_facts(
        _xypk("line", style_ref=1, facts=2, trace_id=11),
        [[0.0, 1.0, 2.0], [0.0, 1.0, 0.0], None, None, None, None, None],
    )
    assert list(kinds) == [1, 1, 1]
    assert list(ids) == [11, 11, 11]
    assert list(modes) == [11, 11, 11]
    assert coords[0].tolist() == [0.0, 1.0, 2.0]


def test_pack_product_facts_ignores_polar_smooth() -> None:
    kinds, ids, refs, diameters, symbols, modes, coords = scene_pack_product_facts(
        _xypk("line", coords=1, facts=2, trace_id=4),
        [[0.0, 1.0], [0.0, 1.0], None, None, None, None, None],
    )
    assert list(modes) == [0, 0]
    assert coords[0].tolist() == [0.0, 1.0]


def test_pack_product_heatmap_reads_range_endpoints() -> None:
    kinds, ids, refs, diameters, symbols, modes, coords = scene_pack_product(
        "heatmap",
        [[1.0, 3.0], [2.0, 4.0], None, None, None, None, None],
        flags=2,
        style_ref=9,
        trace_id=11,
        extra0=2.0,
        extra1=3.0,
    )
    assert list(kinds) == [2, 2]
    assert list(modes) == [9, 9]
    assert list(diameters) == [2.0, 3.0]
    assert coords[0].tolist() == [1.0, 0.0]
    assert coords[1].tolist() == [2.0, 0.0]
    assert coords[2].tolist() == [3.0, 0.0]
    assert coords[3].tolist() == [4.0, 0.0]


def _annotation_mark_row(
    kind: int,
    axis: int,
    symbol: int,
    style_ref: int,
    index: int,
    value0: float,
    value1: float,
    size: float,
) -> bytes:
    return struct.pack(
        "<BBBBIIxxxxddd",
        kind,
        axis,
        symbol,
        0,
        style_ref,
        index,
        value0,
        value1,
        size,
    )


def test_pack_annotation_marks_rule_spans_the_opposite_axis() -> None:
    kinds, ids, refs, diameters, symbols, modes, coords = scene_pack_annotation_marks(
        _annotation_mark_row(1, 0, 0, 3, 7, 1.5, 0.0, 0.0),
        x_domain=(0.0, 4.0),
        y_domain=(10.0, 20.0),
    )
    assert list(kinds) == [1, 1]
    assert list(ids) == [0x5859000000000000 | (1 << 40) | 7] * 2
    assert list(refs) == [3, 3]
    assert list(modes) == [0, 0]
    assert coords[0].tolist() == [1.5, 1.5]
    assert coords[1].tolist() == [10.0, 20.0]


def test_pack_annotation_marks_y_band_uses_tag_four() -> None:
    kinds, ids, refs, diameters, symbols, modes, coords = scene_pack_annotation_marks(
        _annotation_mark_row(2, 1, 0, 1, 2, 3.0, 5.0, 0.0),
        x_domain=(0.0, 10.0),
        y_domain=(-1.0, 1.0),
    )
    assert list(kinds) == [2]
    assert list(ids) == [0x5859000000000000 | (4 << 40) | 2]
    assert coords[0].tolist() == [0.0]
    assert coords[1].tolist() == [3.0]
    assert coords[2].tolist() == [10.0]
    assert coords[3].tolist() == [5.0]


def test_pack_annotation_marks_marker_keeps_point_size_and_symbol() -> None:
    kinds, ids, refs, diameters, symbols, modes, coords = scene_pack_annotation_marks(
        _annotation_mark_row(3, 0, 4, 8, 9, 1.0, 2.0, 6.0),
        x_domain=(0.0, 1.0),
        y_domain=(0.0, 1.0),
    )
    assert list(kinds) == [0]
    assert list(symbols) == [4]
    assert list(diameters) == [6.0]
    assert list(ids) == [0x5859000000000000 | (3 << 40) | 9]
    assert coords[0].tolist() == [1.0]
    assert coords[1].tolist() == [2.0]


def test_pack_annotation_marks_rejects_bad_kind_and_nonfinite_domain() -> None:
    with pytest.raises(ValueError, match="invalid scene annotation packing"):
        scene_pack_annotation_marks(
            _annotation_mark_row(9, 0, 0, 0, 0, 0.0, 0.0, 1.0),
            x_domain=(0.0, 1.0),
            y_domain=(0.0, 1.0),
        )
    with pytest.raises(ValueError, match="must be finite"):
        scene_pack_annotation_marks(
            _annotation_mark_row(1, 0, 0, 0, 0, 0.0, 0.0, 0.0),
            x_domain=(0.0, float("nan")),
            y_domain=(0.0, 1.0),
        )


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


def test_pack_annotations_frames_xyad_v2_plain_text() -> None:
    framed = scene_pack_annotations(
        text_meta=struct.pack(
            "<dd4s4s4sdB3x",
            0.5,
            0.25,
            bytes((102, 112, 133, 255)),
            bytes(4),
            bytes(4),
            0.0,
            0,
        ),
        text_lens=[2],
        texts=b"hi",
        attached_meta=b"",
        attached_lens=[],
        attached_texts=b"",
        arrow_meta=b"",
        callout_meta=b"",
        callout_lens=[],
        callout_texts=b"",
        wrapped_meta=b"",
        wrapped_lens=[],
        wrapped_texts=b"",
    )
    assert framed[:4] == b"XYAD"
    assert int.from_bytes(framed[4:8], "little") == 2
    assert framed[24:28] == b"XYAT"
    assert int.from_bytes(framed[28:32], "little") == 1
    assert framed[24 + 12 + 24 : 24 + 12 + 26] == b"hi"


def test_named_text_annotation_compiles_through_rust_xyad() -> None:
    figure = Figure().text(0.5, 0.5, "note", color="#667085")
    encoded = figure_scene(figure)
    assert encoded
    assert b"note" in encoded


def test_pack_annotation_facts_frames_text_and_expands_rule() -> None:
    text = (
        struct.pack(
            "<4sIIBBBBIIBBHI18d4s4s4s4s4sI8f",
            b"XYAF",
            1,
            0,
            0,
            0,
            0,
            255,
            (1 << 1) | (1 << 5) | (1 << 6),
            1,
            255,
            0,
            0,
            2,
            0.5,
            0.25,
            *[float("nan")] * 16,
            bytes((102, 112, 133, 255)),
            bytes(4),
            bytes(4),
            bytes(4),
            bytes(4),
            0,
            *[0.0] * 8,
        )
        + b"hi"
    )
    framed = scene_pack_annotation_facts(
        text,
        style_ref_base=0,
        x_domain=(0.0, 1.0),
        y_domain=(0.0, 1.0),
    )
    assert framed[:4] == b"XYAO"
    xyad_len = int.from_bytes(framed[16:20], "little")
    xyad = framed[32 : 32 + xyad_len]
    assert xyad[:4] == b"XYAD"
    assert b"XYAT" in xyad
    assert b"hi" in xyad

    rule = struct.pack(
        "<4sIIBBBBIIBBHI18d4s4s4s4s4sI8f",
        b"XYAF",
        1,
        7,
        3,
        1,
        0,
        255,
        (1 << 11) | (1 << 15),
        1,
        255,
        0,
        0,
        0,
        *[float("nan")] * 9,
        1.5,
        *[float("nan")] * 8,
        bytes((102, 112, 133, 255)),
        bytes(4),
        bytes(4),
        bytes(4),
        bytes(4),
        0,
        *[0.0] * 8,
    )
    packed = scene_pack_annotation_facts(
        rule,
        style_ref_base=2,
        x_domain=(0.0, 10.0),
        y_domain=(-1.0, 1.0),
    )
    assert int.from_bytes(packed[8:12], "little") == 1
    assert int.from_bytes(packed[12:16], "little") == 2
    assert int.from_bytes(packed[32 + 56 + 4 : 32 + 56 + 8], "little") == 2


def test_pack_heatmap_facts_named_plane_kind() -> None:
    grid = struct.pack("<2d", 0.25, 0.75)
    name = b"viridis"
    facts = (
        struct.pack(
            "<4sIQIIIB3x4d",
            b"XYHF",
            1,
            9,
            1,
            2,
            (1 << 2) | (1 << 5) | (1 << 12),
            0,
            0.0,
            1.0,
            float("nan"),
            float("nan"),
        )
        + grid
        + struct.pack("<I", len(name))
        + name
    )
    plane = scene_pack_heatmap_facts(facts)
    assert int.from_bytes(plane[16:20], "little") == 2
    assert plane.endswith(name)


def test_pack_heatmap_facts_truecolor_without_grid_skips() -> None:
    facts = struct.pack(
        "<4sIQIIIB3x4d",
        b"XYHF",
        1,
        1,
        1,
        1,
        1 << 7,
        0,
        float("nan"),
        float("nan"),
        float("nan"),
        float("nan"),
    )
    assert scene_pack_heatmap_facts(facts) == b""


def test_pack_scene_extras_dash_facts_encode_xyds() -> None:
    prefix = struct.pack(
        "<IBBBBBBBBI8f",
        0,
        1,
        2,
        255,
        0,
        0,
        0,
        0,
        0,
        0,
        4.0,
        2.0,
        0.0,
        0.0,
        0.0,
        0.0,
        0.0,
        0.0,
    )
    facts = struct.pack("<4sIII", b"XYSS", 1, 1, 0) + prefix
    extras = scene_pack_scene_extras(b"", b"", facts)
    assert extras[:4] == b"XYDS"
    assert int.from_bytes(extras[8:12], "little") == 1


def test_pack_scene_extras_empty_inputs_are_empty() -> None:
    assert scene_pack_scene_extras(b"", b"", b"") == b""


def test_pack_scene_extras_polar_and_paint_wrap_xyex() -> None:
    polar = bytearray(92)
    polar[:4] = b"XYPL"
    paint = bytearray(16)
    paint[:4] = b"XYHP"
    extras = scene_pack_scene_extras(bytes(polar), bytes(paint), b"")
    assert extras[:4] == b"XYEX"
    assert int.from_bytes(extras[4:8], "little") == 1
    assert int.from_bytes(extras[8:12], "little") == 92


def test_pack_density_grid_encodes_log_u8_lattice() -> None:
    packed = scene_pack_density_grid(
        [0.25, 0.75],
        [0.25, 0.75],
        0.0,
        1.0,
        0.0,
        1.0,
    )
    assert packed is not None
    encoded, gmax, mean, rows, cols = packed
    assert (cols, rows) == (512, 384)
    assert encoded.size == 512 * 384
    assert mean is None
    assert gmax > 0.0
    assert int(encoded.max()) > 0


def test_pack_density_grid_skips_empty_columns() -> None:
    assert (
        scene_pack_density_grid(
            [],
            [],
            0.0,
            1.0,
            0.0,
            1.0,
        )
        is None
    )


def test_pack_public_export_empty_figure_is_xyep() -> None:
    facts = struct.pack("<4sIIIIIIII", b"XYEF", 1, 0, 0, 0, 0, 0, 0, 0)
    envelope = scene_pack_public_export(facts)
    assert envelope[:4] == b"XYEP"
    assert int.from_bytes(envelope[4:8], "little") == 1
    assert len(envelope) == 36


def test_pack_figure_chrome_empty_facts_is_xycc() -> None:
    from xyg import _scene_v3

    figure = Figure(width=400, height=300)
    figure.axis_options["x"]["domain"] = (0.0, 1.0)
    figure.axis_options["y"]["domain"] = (0.0, 1.0)
    figure.scatter([0.0, 1.0], [0.0, 1.0])
    facts = _scene_v3._pack_chrome_facts(
        figure,
        [],
        [],
        width=400,
        height=300,
        margins=None,
        colorbar_ok=True,
    )
    envelope = scene_pack_figure_chrome(facts)
    assert envelope[:4] == b"XYCC"
    assert int.from_bytes(envelope[4:8], "little") == 1
    chrome = _scene_v3._unpack_xycc(envelope)
    assert len(chrome["chrome_style"]) == 200
    assert chrome["x_major_ticks"] is None
    assert chrome["legend_input"] == b""
    scene = figure_scene(figure)
    assert int.from_bytes(scene[4:8], "little") == 31


def test_pack_figure_chrome_rejects_empty_authored_legend_loc() -> None:
    figure = Figure(width=240, height=160)
    figure.scatter([0.25], [0.5], name="observed")
    figure.legend_options = {"loc": ""}
    with pytest.raises(UnsupportedSceneV3, match="location"):
        figure_scene(figure)


def test_pack_figure_chrome_tick_overflow_keeps_encode_message() -> None:
    from xyg import _scene_v3

    figure = Figure(width=400, height=300)
    figure.axis_options["x"]["domain"] = (0.0, 1.0)
    figure.axis_options["y"]["domain"] = (0.0, 1.0)
    figure.axis_options["x"]["tick_values"] = list(range(201))
    figure.scatter([0.0, 1.0], [0.0, 1.0])
    facts = _scene_v3._pack_chrome_facts(
        figure,
        [],
        [],
        width=400,
        height=300,
        margins=None,
        colorbar_ok=True,
    )
    with pytest.raises(ValueError, match="axis tick lists are limited"):
        scene_pack_figure_chrome(facts)
