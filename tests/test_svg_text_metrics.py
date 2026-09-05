"""Focused static-text layout regressions shared by SVG and native export."""

from __future__ import annotations

import xml.etree.ElementTree as ET

import pytest

from xyg import _fontmetrics, _native, _svg, _textblock


def test_text_box_width_uses_embedded_advances_with_unknown_glyph_fallback() -> None:
    font_size = 11.0

    assert _svg._estimated_text_width(["gamma"], font_size) == pytest.approx(
        _fontmetrics.advance("gamma", font_size)
    )
    assert _svg._estimated_text_width(["iiii", "gamma"], font_size) == pytest.approx(
        _fontmetrics.advance("gamma", font_size)
    )
    assert _svg._estimated_text_width(["🦉"], font_size) == pytest.approx(font_size)
    assert _svg._estimated_text_width([], font_size) == 0.0


@pytest.mark.xfail(
    reason="XYST static route admission gap; tracked in #889.",
    strict=False,
)
def test_svg_mathtext_ranges_are_sorted_clamped_and_merged_without_duplicate_text() -> None:
    rendered = _svg._svg_mathtext_spans(
        "abcdef",
        {"math_italic_ranges": "2:4,0:3,2:4,-5:1,5:99"},
        0,
    )
    root = ET.fromstring(f"<text>{rendered}</text>")

    assert "".join(root.itertext()) == "abcdef"
    assert [node.text for node in root if node.tag.endswith("tspan")] == ["abcd", "f"]


@pytest.mark.xfail(
    reason="XYST static route admission gap; tracked in #889.",
    strict=False,
)
def test_left_gutter_measures_y_tick_labels_once_for_an_outside_title(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = 0

    def measured_room(axis: dict[str, object], plot_h: float) -> tuple[float, float]:
        nonlocal calls
        calls += 1
        assert axis["label"] == "Y"
        assert plot_h == 300.0
        return 7.0, 23.0

    monkeypatch.setattr(_svg, "_y_tick_label_room", measured_room)
    label_size = 12.0
    spec = {
        "x_axis": {},
        "y_axis": {
            "label": "Y",
            "side": "left",
            "style": {"label_size": label_size},
        },
    }

    room = _svg._y_axis_left_room(spec, 300.0)
    ascent, descent = _svg._text_cell(label_size)
    expected = (
        _svg._AXIS_TEXT_EDGE_PAD
        + ascent
        + descent
        + _svg._Y_TITLE_TICK_GAP * label_size
        + 7.0
        + 23.0
    )

    assert calls == 1
    assert room == pytest.approx(expected)


def test_measurements_are_reused_only_within_one_layout_pass(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = 0
    original = _native.text_block_measure

    def measured(
        text: object,
        font_size: float,
        line_height: float = 1.2,
        max_width: float | None = None,
    ) -> dict[str, object]:
        nonlocal calls
        calls += 1
        return original(text, font_size, line_height=line_height, max_width=max_width)

    monkeypatch.setattr(_native, "text_block_measure", measured)
    with _textblock.measurement_cache():
        first = _textblock.measure("first\r\nsecond", 12.0)
        second = _textblock.measure("first\nsecond", 12.0)

    assert second is first
    assert calls == 1

    with _textblock.measurement_cache():
        _textblock.measure("first\nsecond", 12.0)
    assert calls == 2


@pytest.mark.xfail(
    reason="XYST static route admission gap; tracked in #889.",
    strict=False,
)
def test_default_layout_resolves_x_tick_room_once_when_y_gutter_does_not_grow(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = 0
    original = _svg._x_axis_rooms

    def measured(
        axes: dict[str, dict[str, object]],
        plot_w: float,
        compact: bool,
    ) -> tuple[float, float, float]:
        nonlocal calls
        calls += 1
        return original(axes, plot_w, compact)

    monkeypatch.setattr(_svg, "_x_axis_rooms", measured)

    def unexpected_label_layout(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("ordinary numeric x ticks must keep the fixed single-line band")

    monkeypatch.setattr(_svg, "_axis_tick_label_layout", unexpected_label_layout)
    spec = {
        "width": 640,
        "height": 480,
        "x_axis": {"range": [0.0, 1.0]},
        "y_axis": {"range": [0.0, 1.0], "side": "left"},
    }

    _svg.layout(spec)

    assert calls == 1


def test_scene_layout_rooms_match_rust_cartesian_gutters() -> None:
    spec = {
        "width": 320,
        "height": 240,
        "x_axis": {"kind": "linear", "domain": [0.0, 4.0], "range": [0.0, 4.0]},
        "y_axis": {"kind": "linear", "domain": [0.0, 5.0], "range": [0.0, 5.0]},
        "title": "Hello title",
    }
    rooms = _svg.scene_layout_rooms(spec)
    expected = _native.scene_plot_layout(
        viewport=(320.0, 240.0),
        x_axis=(0, 0.0, 4.0, 1.0, False),
        y_axis=(0, 0.0, 5.0, 1.0, False),
        title="Hello title",
    )
    assert rooms == expected
    width, height, _compact, plot = _svg.layout(spec)
    compat = (
        plot["x"],
        width - plot["x"] - plot["w"],
        plot["y"],
        height - plot["y"] - plot["h"],
    )
    assert compat != expected


def test_scene_layout_rooms_fail_closed_for_custom_font_and_polar() -> None:
    base = {
        "width": 320,
        "height": 240,
        "x_axis": {"kind": "linear", "domain": [0.0, 1.0]},
        "y_axis": {"kind": "linear", "domain": [0.0, 1.0]},
    }
    custom = {**base, "chrome_styles": {"title": {"font-family": "Comic Sans"}}}
    polar = {**base, "coords": "polar"}
    category = {
        **base,
        "x_axis": {"kind": "category", "domain": [0.0, 1.0]},
    }
    assert _svg.scene_layout_rooms(custom) is None
    assert _svg.scene_layout_rooms(polar) is None
    assert _svg.scene_layout_rooms(category) is None
    top_x = {**base, "x_axis": {**base["x_axis"], "side": "top"}}
    right_y = {**base, "y_axis": {**base["y_axis"], "side": "right"}}
    outside = {**base, "show_legend": True, "legend": {"loc": "outside right"}}
    axes_bar = {**base, "colorbar": {"placement": "axes", "orientation": "vertical"}}
    assert _svg.scene_layout_rooms(top_x) is None
    assert _svg.scene_layout_rooms(right_y) is None
    assert _svg.scene_layout_rooms(outside) is None
    assert _svg.scene_layout_rooms(axes_bar) is None
