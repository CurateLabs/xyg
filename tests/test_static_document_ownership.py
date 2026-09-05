"""Execute public static journeys while trapping legacy Python render policy."""

from __future__ import annotations

import io
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from os import PathLike
from pathlib import Path
from types import FrameType

import pytest

import xyg
from xyg import export
from xyg._static_document import UnsupportedStaticExport
from xyg.components import Component

FORMATS = ("svg", "png", "pdf", "jpeg", "webp")


@contextmanager
def _product_calls(
    *, reject_legacy: bool = True, queries: list[str] | None = None
) -> Iterator[list[str]]:
    """Observe actual calls, including functions imported before this guard."""
    calls: list[str] = []
    previous = sys.getprofile()

    def profile(frame: FrameType, event: str, _arg: object) -> None:
        if event != "call":
            return
        module = str(frame.f_globals.get("__name__", ""))
        name = frame.f_code.co_name
        leaf = module.rsplit(".", 1)[-1]
        if module == "xyg._native" and name == "static_document_export":
            calls.append(str(frame.f_locals.get("format")))
        if module == "xyg._native" and name == "static_legend_fit" and queries is not None:
            queries.append(name)
        forbidden = module.startswith("xyg.") and (
            leaf.startswith("_export_")
            or leaf in {"_raster_render", "_svg_render"}
            or (leaf == "_facets_grid" and name == "_compose_rgba")
        )
        if reject_legacy and forbidden:
            raise AssertionError(f"legacy Python static policy executed: {module}.{name}")

    sys.setprofile(profile)
    try:
        yield calls
    finally:
        sys.setprofile(previous)


def _chart(*annotations: Component):
    return xyg.chart(
        xyg.line("x", "y", data={"x": [0, 1, 2], "y": [1, 3, 2]}),
        *annotations,
        width=240,
        height=180,
    )


def _assert_format(data: bytes, format: str) -> None:
    if format == "svg":
        assert data.startswith(b"<svg ")
        assert b"</svg>" in data
    elif format == "png":
        assert data.startswith(b"\x89PNG\r\n\x1a\n")
    elif format == "pdf":
        assert data.startswith(b"%PDF-")
    elif format == "jpeg":
        assert data.startswith(b"\xff\xd8\xff")
    else:
        assert data[:4] == b"RIFF" and data[8:12] == b"WEBP"


@pytest.mark.parametrize("surface", ["chart", "figure"])
@pytest.mark.parametrize("format", FORMATS)
def test_public_static_exports_execute_rust_document(surface: str, format: str) -> None:
    chart = _chart()
    target = chart if surface == "chart" else chart.figure()
    with _product_calls() as calls:
        data = target.to_image(format, scale=1, engine=export.Engine.default)
    assert calls == [format]
    _assert_format(data, format)


@pytest.mark.parametrize("surface", ["chart", "figure"])
def test_direct_svg_and_png_aliases_use_the_document_kernel(surface: str) -> None:
    chart = _chart()
    target = chart if surface == "chart" else chart.figure()
    with _product_calls() as calls:
        svg = target.to_svg()
        png = target.to_png(scale=1, engine=export.Engine.default)
    assert calls == ["svg", "png"]
    _assert_format(svg.encode(), "svg")
    _assert_format(png, "png")


def test_public_write_image_uses_document_kernel(tmp_path: Path) -> None:
    path = tmp_path / "chart.pdf"
    with _product_calls() as calls:
        _chart().write_image(path, engine=export.Engine.default)
    assert calls == ["pdf"]
    _assert_format(path.read_bytes(), "pdf")


def test_native_batch_uses_document_kernel_for_every_member(tmp_path: Path) -> None:
    figures = [_chart().figure() for _ in FORMATS]
    paths: list[str | PathLike[str]] = [tmp_path / f"batch.{format}" for format in FORMATS]
    with _product_calls() as calls:
        outputs = export.write_images(figures, paths, scale=1, engine=export.Engine.default)
    assert calls == list(FORMATS)
    for format, path, data in zip(FORMATS, paths, outputs, strict=True):
        assert Path(path).read_bytes() == data
        _assert_format(data, format)


@pytest.mark.parametrize("format", FORMATS)
def test_facet_static_exports_execute_rust_document(format: str) -> None:
    chart = xyg.facet_chart(
        xyg.line(x="x", y="y"),
        by="group",
        data={"x": [0, 1, 0, 1], "y": [1, 2, 2, 1], "group": ["a", "a", "b", "b"]},
        width=412,
        height=160,
        cols=2,
    )
    with _product_calls() as calls:
        data = chart.to_image(format, scale=1, engine=export.Engine.default)
    assert calls == [format]
    _assert_format(data, format)


@pytest.mark.parametrize("format", ["svg", "png"])
@pytest.mark.parametrize("panels", [1, 2])
def test_pyplot_native_savefig_executes_rust_document(format: str, panels: int) -> None:
    from xyg.pyplot._mplfig import Figure

    figure = Figure(1, figsize=(4, 3), dpi=60)
    for index in range(panels):
        axes = figure.add_subplot(1, panels, index + 1)
        axes.plot([0, 1, 2], [1, 3, 2])
        axes.set_xlabel("x")
        axes.set_ylabel("y")
        axes.text(1, 2, "note", fontsize=12)
    figure.suptitle("Shared title")
    output = io.BytesIO()
    with _product_calls() as calls:
        figure.savefig(output, format=format)
    assert calls == [format]
    _assert_format(output.getvalue(), format)


@pytest.mark.parametrize("format", ["svg", "png"])
@pytest.mark.parametrize("location", ["best", "upper right"])
def test_pyplot_legend_placement_does_not_execute_legacy_policy(format: str, location: str) -> None:
    from xyg.pyplot._mplfig import Figure

    figure = Figure(1, figsize=(4, 3), dpi=60)
    axes = figure.add_subplot(1, 1, 1)
    axes.plot([0, 1, 2], [1, 3, 2], label="Series")
    axes.legend(loc=location)
    output = io.BytesIO()
    queries: list[str] = []
    with _product_calls(queries=queries) as calls:
        figure.savefig(output, format=format)
    assert calls == [format]
    assert bool(queries) == (location == "best")
    _assert_format(output.getvalue(), format)


@pytest.mark.parametrize(
    ("styles", "reason"),
    [
        ([{"font_family": "serif"}], "XYG_STATIC_UNSUPPORTED_CUSTOM_FONT"),
        ([{"math_italic_ranges": "0:1"}], "XYG_STATIC_UNSUPPORTED_MATHTEXT_STYLE"),
        (
            [{"font_size": 12}, {"font_size": 18}],
            "XYG_STATIC_UNSUPPORTED_HETEROGENEOUS_ANNOTATION_STYLE",
        ),
    ],
)
def test_unrepresented_annotation_facts_fail_before_rendering(
    styles: list[dict], reason: str
) -> None:
    chart = _chart(*(xyg.text(index, 2, "note", style=style) for index, style in enumerate(styles)))
    with _product_calls() as calls, pytest.raises(UnsupportedStaticExport) as error:
        chart.to_image("svg", engine=export.Engine.default)
    assert str(error.value) == reason
    assert calls == []


def test_html_keeps_authored_css_and_font_without_native_static_kernel() -> None:
    chart = _chart(xyg.text(1, 2, "browser label", style={"font_family": "serif"}))
    css = ".xy-chart { background: rgb(1, 2, 3); }"
    with _product_calls(reject_legacy=False) as calls:
        document = chart.to_html(custom_css=css)
    assert css in document
    assert "serif" in document and "browser label" in document
    assert calls == []
