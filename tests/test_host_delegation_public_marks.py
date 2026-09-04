"""Executable public-mark journeys used by the semantic ownership proof (#874)."""

from __future__ import annotations

from collections.abc import Callable, Iterable

import pytest

import xyg
from xyg._figure import Figure


def _single(mark: object) -> list[Figure]:
    return [xyg.chart(mark).figure()]


MARK_JOURNEYS: dict[str, Callable[[], Iterable[Figure]]] = {
    "area": lambda: _single(xyg.area(x=[0.0, 1.0], y=[1.0, 2.0])),
    "bar": lambda: _single(xyg.bar(x=[0.0, 1.0], y=[1.0, 2.0])),
    "box": lambda: _single(xyg.box(values=[[1.0, 2.0], [2.0, 3.0]])),
    "column": lambda: _single(xyg.column(x=[0.0, 1.0], y=[1.0, 2.0])),
    "contour": lambda: _single(xyg.contour(z=[[1.0, 2.0], [2.0, 3.0]])),
    "ecdf": lambda: _single(xyg.ecdf(values=[1.0, 2.0, 3.0])),
    "error_band": lambda: _single(xyg.error_band(x=[0.0, 1.0], lower=[1.0, 2.0], upper=[2.0, 3.0])),
    "errorbar": lambda: _single(xyg.errorbar(x=[0.0, 1.0], y=[1.0, 2.0], yerr=0.2)),
    "graph": lambda: _single(xyg.graph(["a", "b"], [("a", "b")], layout="circle")),
    "heatmap": lambda: _single(xyg.heatmap(z=[[1.0, 2.0], [3.0, 4.0]])),
    "hexbin": lambda: _single(xyg.hexbin(x=[0.0, 1.0], y=[1.0, 2.0])),
    "histogram": lambda: _single(xyg.histogram(values=[1.0, 2.0, 3.0], bins=2)),
    "line": lambda: _single(xyg.line(x=[0.0, 1.0], y=[1.0, 2.0])),
    "radar": lambda: [xyg.radar_chart(["a", "b", "c"], xyg.area([1.0, 2.0, 1.5])).figure()],
    "ribbon": lambda: _single(xyg.ribbon([0.0], [1.0], [0.0], [0.4], [0.2], [0.6])),
    "sankey": lambda: _single(xyg.sankey([("a", "b", 1.0)])),
    "scatter": lambda: _single(xyg.scatter(x=[0.0, 1.0], y=[1.0, 2.0])),
    "segments": lambda: _single(xyg.segments(x0=[0.0], y0=[0.0], x1=[1.0], y1=[1.0])),
    "stairs": lambda: _single(xyg.stairs(values=[1.0, 2.0], edges=[0.0, 1.0, 2.0])),
    "stem": lambda: _single(xyg.stem(x=[0.0, 1.0], y=[1.0, 2.0])),
    "step": lambda: _single(xyg.step(x=[0.0, 1.0], y=[1.0, 2.0])),
    "triangle_mesh": lambda: _single(
        xyg.triangle_mesh(x0=[0.0], y0=[0.0], x1=[1.0], y1=[0.0], x2=[0.5], y2=[1.0])
    ),
    "violin": lambda: _single(xyg.violin(values=[[1.0, 2.0], [2.0, 3.0]])),
    "polar": lambda: [xyg.polar_chart(xyg.line([0.0, 1.0], [1.0, 2.0])).figure()],
    "pie": lambda: [xyg.pie_chart(["a", "b"], [1.0, 2.0]).figure()],
    "wind_rose": lambda: [xyg.wind_rose([0.0, 90.0], [1.0, 2.0], sectors=4).figure()],
    "facet": lambda: (
        xyg.facet_chart(
            xyg.line(x="x", y="y"),
            by="g",
            data={"x": [0.0, 1.0], "y": [1.0, 2.0], "g": ["a", "b"]},
        )
        .figure()
        .figures
    ),
}


@pytest.mark.parametrize("kind", sorted(MARK_JOURNEYS))
def test_every_public_mark_reaches_a_rust_owned_payload_route(kind: str) -> None:
    figures = list(MARK_JOURNEYS[kind]())
    assert figures, f"{kind} did not produce a figure"
    for figure in figures:
        spec, _blob = figure.build_payload(px_width=320)
        assert spec["traces"], f"{kind} produced no canonical payload traces"
