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


def _y2_labels(svg: str) -> list[str]:
    return [t for a, t in _texts(svg) if a.get("text-anchor") == "start"]


def _dual_with(raw: dict[str, Any] | None = None, **y2: Any):
    figure = dual_chart(y2=y2).figure()
    figure.axis_options["y2"].update(raw or {})
    return figure


def _svg_of(figure: Any) -> str:
    from xyg._static_document import export_figure

    return export_figure(figure, "svg", width=WIDTH, height=HEIGHT).decode("utf-8")


def test_authored_min_gap_thins_y2_labels_like_the_primary_axis() -> None:
    assert _y2_labels(_svg_of(_dual_with())) == ["0", "100", "200", "300", "400"]
    assert _y2_labels(_svg_of(_dual_with(tick_label_min_gap=200))) == ["0", "400"]


def test_authored_strategy_and_collision_reach_rust_with_strategy_first() -> None:
    gap = {"tick_label_min_gap": 200}
    every = ["0", "100", "200", "300", "400"]
    assert _y2_labels(_svg_of(_dual_with(tick_label_strategy="preserve", **gap))) == every
    assert _y2_labels(_svg_of(_dual_with({"collision": "preserve"}, **gap))) == every
    # `tick_label_strategy` takes precedence over the legacy `collision` key.
    both = _dual_with({"collision": "hide"}, tick_label_strategy="preserve", **gap)
    assert _y2_labels(_svg_of(both)) == every
    assert _y2_labels(_svg_of(_dual_with({"collision": "hide"}, **gap))) == ["0", "400"]


def test_symlog_y2_places_zero_at_the_middle_of_the_plot() -> None:
    chart = c.line_chart(
        c.line(x=[1, 2, 3], y=[1, 2, 3]),
        c.line(x=[1, 2, 3], y=[-50, 0, 50], y_axis="y2"),
        c.x_axis(domain=(0, 4)),
        c.y_axis(domain=(0, 4)),
        c.y_axis(id="y2", side="right", type_="symlog", constant=2, domain=(-100, 100)),
        width=WIDTH,
        height=HEIGHT,
    )
    svg = chart.to_svg()
    plot = re.search(
        r'data-xy-chrome="plot-background" x="[\d.]+" y="([\d.]+)" width="[\d.]+" height="([\d.]+)"',
        svg,
    )
    middle = float(plot.group(1)) + float(plot.group(2)) / 2
    _below, at_zero, _above = _polyline_ys(svg)[1]
    assert at_zero == pytest.approx(middle, abs=0.01)
    labels = {t: float(a["y"]) for a, t in _texts(svg) if a.get("text-anchor") == "start"}
    # The authored constant (2) shapes the ladder; an unauthored one would not.
    assert set(labels) == {"-12.78", "0.00", "12.78"}
    assert labels["0.00"] == pytest.approx(middle, abs=6)


def test_category_y2_is_rejected_by_rust() -> None:
    figure = c.line_chart(
        c.line(x=[1, 2, 3], y=[1, 2, 3]),
        c.line(x=[1, 2, 3], y=["a", "b", "c"], y_axis="y2"),
        c.x_axis(domain=(0, 4)),
        c.y_axis(domain=(0, 4)),
        c.y_axis(id="y2", side="right"),
    ).figure()
    assert figure._axis_kind("y2") == "category"
    assert _reason(figure) == "XYG_SCENE_UNSUPPORTED_PUBLIC_AXIS"


def _raster_title_angle(figure: Any, text: bytes) -> float:
    import struct

    from xyg._scene_v3 import figure_raster_commands

    commands = figure_raster_commands(figure)
    at = commands.index(text)
    # ... angle f32 | flags u8 | reserved u32 | rgba [4] | len u32 | text
    return struct.unpack("<f", commands[at - 17 : at - 13])[0]


def test_y2_title_reads_bottom_to_top_in_svg_pdf_and_raster() -> None:
    svg = dual_chart().to_svg()
    transforms = {t: a["transform"].split(" ")[0] for a, t in _texts(svg) if t in {"L", "R"}}
    # Same orientation as the left title and Matplotlib's twinx label (rotation 90).
    assert transforms == {"L": "rotate(-90", "R": "rotate(-90"}
    assert _raster_title_angle(dual_chart().figure(), b"R") == -90.0
    pdf = dual_chart().to_image("pdf")
    assert pdf.startswith(b"%PDF")


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


def test_annotation_bound_to_y2_is_refused_by_rust() -> None:
    """`xyg.text(..., y_axis="y2")` used to project through the primary scale."""

    def annotated(annotation: Any):
        chart = c.line_chart(
            c.line(x=[1, 2, 3], y=[1, 2, 3]),
            c.line(x=[1, 2, 3], y=[100, 200, 300], y_axis="y2"),
            c.x_axis(domain=(0, 4)),
            c.y_axis(domain=(0, 4)),
            c.y_axis(id="y2", side="right", domain=(0, 400)),
            annotation,
        )
        return chart.figure()

    refused = "XYG_SCENE_UNSUPPORTED_Y2_ANNOTATION:"
    for annotation in (
        c.text(2, 200, "secondary", y_axis="y2"),
        c.text(2, 200, "s", y_axis="y2", style={"coordinate_space": "yaxis_transform"}),
        c.callout(2, 200, "s", y_axis="y2"),
        c.marker(2, 200, y_axis="y2"),
        c.hline(200, y_axis="y2"),
    ):
        assert (_reason(annotated(annotation)) or "").startswith(refused), annotation.kind
    admitted = c.text(2, 0.5, "s", y_axis="y2", style={"coordinate_space": "axes_fraction"})
    assert _reason(annotated(admitted)) is None
    assert _reason(annotated(c.text(2, 2, "primary"))) is None
    with pytest.raises(ValueError, match="annotation y_axis"):
        c.text(2, 2, "s", y_axis="y3")
