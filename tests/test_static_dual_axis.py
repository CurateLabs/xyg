"""Static export of the native secondary right-hand y axis (`y2`, twinx; #1006).

Public composition only: `xyg.y_axis(id="y2", side="right")` plus a mark bound
with `y_axis="y2"`. Rust owns admission, layout and painting; these tests pin
what the Python host marshals (selector, scale, chrome facts) and that Rust's
stable reasons surface unchanged.
"""

from __future__ import annotations

import re
from typing import Any

import pytest

import xyg.components as c
from xyg._scene_v3 import scene_export_support_reason

WIDTH = 480
HEIGHT = 320


def dual_chart(
    *, y: dict[str, Any] | None = None, y2: dict[str, Any] | None = None, y2_side="right"
):
    return c.line_chart(
        c.line(x=[1, 2, 3], y=[1, 2, 3]),
        c.line(x=[1, 2, 3], y=[100, 200, 300], y_axis="y2"),
        c.x_axis(domain=(0, 4)),
        c.y_axis(domain=(0, 4), label="L", **(y or {})),
        c.y_axis(id="y2", side=y2_side, label="R", domain=(0, 400), **(y2 or {})),
        width=WIDTH,
        height=HEIGHT,
    )


def _texts(svg: str) -> list[tuple[dict[str, str], str]]:
    return [
        (dict(re.findall(r'([\w-]+)="([^"]*)"', attrs)), body)
        for attrs, body in re.findall(r"<text([^>]*)>([^<]*)</text>", svg)
    ]


def _polyline_ys(svg: str) -> list[list[float]]:
    return [
        [float(pair.split(",")[1]) for pair in points.split()]
        for points in re.findall(r'<polyline points="([^"]*)"', svg)
    ]


def test_y2_marks_use_the_secondary_scale() -> None:
    # 100..300 on a 0..400 y2 scale sit where 1..3 sit on the 0..4 primary
    # scale: only the per-record y selector can place the second line there.
    primary, secondary = _polyline_ys(dual_chart().to_svg())
    assert secondary == pytest.approx(primary)


def test_right_gutter_holds_labels_and_title_inside_the_canvas() -> None:
    svg = dual_chart().to_svg()
    plot_right = float(
        re.search(
            r'data-xy-chrome="plot-background" x="[\d.]+" y="[\d.]+" width="([\d.]+)"', svg
        ).group(1)
    )
    plot_left = float(re.search(r'data-xy-chrome="plot-background" x="([\d.]+)"', svg).group(1))
    right_edge = plot_left + plot_right
    texts = _texts(svg)
    labels = [(a, t) for a, t in texts if a.get("text-anchor") == "start"]
    assert [t for _a, t in labels] == ["0", "100", "200", "300", "400"]
    assert all(float(a["x"]) > right_edge for a, _t in labels)
    assert all(float(a["x"]) < WIDTH for a, _t in texts)
    title = next(a for a, t in texts if t == "R")
    assert float(title["x"]) > max(float(a["x"]) for a, _t in labels)
    assert float(title["x"]) < WIDTH


def test_y2_chrome_style_reaches_the_right_axis_only() -> None:
    chart = dual_chart(
        y={"style": {"label_color": "#1f77b4"}},
        y2={
            "style": {
                "label_color": "#d62728",
                "tick_label_color": "#2ca02c",
                "tick_label_size": 20,
                "tick_padding": 12,
            }
        },
    )
    texts = _texts(chart.to_svg())
    title = next(a for a, t in texts if t == "R")
    left_title = next(a for a, t in texts if t == "L")
    assert title["fill"] == "rgba(214,39,40,1.000000)"
    assert left_title["fill"] == "rgba(31,119,180,1.000000)"
    right_labels = [a for a, t in texts if a.get("text-anchor") == "start"]
    assert {a["font-size"] for a in right_labels} == {"20"}
    assert {a["fill"] for a in right_labels} == {"rgba(44,160,44,1.000000)"}


@pytest.mark.parametrize("fmt", ["svg", "png", "pdf"])
def test_every_static_format_exports(fmt: str) -> None:
    data = dual_chart().to_image(fmt)
    magic = {"svg": b"<svg", "png": b"\x89PNG", "pdf": b"%PDF"}[fmt]
    assert magic in data[:64]


def test_explicit_long_labels_widen_the_right_gutter() -> None:
    narrow = dual_chart().to_svg()
    wide = dual_chart(
        y2={"tick_values": [0, 400], "tick_labels": ["0", "1,000,000 units"]}
    ).to_svg()

    def plot_width(svg: str) -> float:
        return float(
            re.search(r'data-xy-chrome="plot-background"[^>]*width="([\d.]+)"', svg).group(1)
        )

    assert plot_width(wide) < plot_width(narrow)
    assert all(float(a["x"]) < WIDTH for a, _t in _texts(wide))


def _reason(figure: Any) -> str | None:
    return scene_export_support_reason(figure)


def test_left_y2_is_rejected_by_rust() -> None:
    assert _reason(dual_chart(y2_side="left").figure()).startswith("XYG_SCENE_UNSUPPORTED_Y2_SIDE:")


def test_x2_is_rejected_by_rust() -> None:
    figure = c.line_chart(
        c.line(x=[1, 2, 3], y=[1, 2, 3]),
        c.x_axis(domain=(0, 4)),
        c.y_axis(domain=(0, 4)),
    ).figure()
    figure.axis_options["x2"] = {"side": "top"}
    assert _reason(figure).startswith("XYG_SCENE_UNSUPPORTED_X2:")


def test_y2_with_colorbar_is_rejected_by_rust() -> None:
    figure = dual_chart().figure()
    figure.colorbar_options = {"title": "c"}
    assert _reason(figure).startswith("XYG_SCENE_UNSUPPORTED_Y2_COLORBAR:")


def test_y2_with_polar_is_rejected_by_rust() -> None:
    figure = dual_chart().figure()
    figure.coords = "polar"
    assert _reason(figure).startswith("XYG_SCENE_UNSUPPORTED_Y2_POLAR:")


def test_y2_axis_without_a_bound_trace_is_rejected_by_rust() -> None:
    figure = c.line_chart(
        c.line(x=[1, 2, 3], y=[1, 2, 3]),
        c.x_axis(domain=(0, 4)),
        c.y_axis(domain=(0, 4)),
        c.y_axis(id="y2", side="right", domain=(0, 400)),
    ).figure()
    assert _reason(figure).startswith("XYG_SCENE_UNSUPPORTED_Y2_TICK_ONLY:")


def test_charts_without_y2_carry_no_y2_block() -> None:
    from xyg._scene_v3 import figure_scene

    figure = c.line_chart(
        c.line(x=[1, 2, 3], y=[1, 2, 3]), c.x_axis(domain=(0, 4)), c.y_axis(domain=(0, 4))
    ).figure()
    assert b"XYY2" not in figure_scene(figure)
    assert b"XYY2" in figure_scene(dual_chart().figure())
