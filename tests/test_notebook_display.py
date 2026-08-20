"""Notebook display-host resolution (reflex-shaped-api.md §3.3).

The widget host needs the anywidget *frontend* extension. A WASM-kernel
deployment with a prebuilt frontend — JupyterLite's `%pip`, e.g.
jupyter.org/try-jupyter — installs only the kernel-side package, so the comm
opens against a frontend that cannot answer it ("No version of module
anywidget is registered"). The kernel cannot observe the frontend registry,
so `show()`/rich display resolve a display host from the runtime instead:
Emscripten kernels fall back to the standalone-HTML iframe (the same isolated
document as `_repr_html_`), and an explicit `display=` argument or
`XY_NOTEBOOK_DISPLAY` overrides the heuristic in both directions.
"""

from __future__ import annotations

import sys
import types

import pytest

import xyg
from xyg import export


@pytest.fixture(autouse=True)
def _no_display_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("XY_NOTEBOOK_DISPLAY", raising=False)


def _chart() -> xyg.Chart:
    return xyg.scatter_chart(
        xyg.scatter([0.0, 1.0, 2.0], [2.0, 4.0, 3.0]),
        xyg.x_axis(label="x"),
        xyg.y_axis(label="y"),
    )


class _StubWidget:
    def __init__(self, figure, **kwargs):
        self.figure = figure


# -- mode resolution ----------------------------------------------------------


def test_default_mode_is_widget() -> None:
    assert export.notebook_display_mode() == "widget"


def test_explicit_argument_wins_over_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("XY_NOTEBOOK_DISPLAY", "widget")
    assert export.notebook_display_mode("html") == "html"


def test_environment_variable_selects_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("XY_NOTEBOOK_DISPLAY", " HTML ")
    assert export.notebook_display_mode() == "html"


def test_empty_environment_variable_means_auto(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("XY_NOTEBOOK_DISPLAY", "")
    assert export.notebook_display_mode() == "widget"


def test_invalid_argument_raises_naming_the_argument() -> None:
    with pytest.raises(ValueError, match=r'display must be one of "auto", "widget", or "html"'):
        export.notebook_display_mode("iframe")


def test_invalid_environment_raises_naming_the_variable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("XY_NOTEBOOK_DISPLAY", "iframe")
    with pytest.raises(ValueError, match="XY_NOTEBOOK_DISPLAY must be one of"):
        export.notebook_display_mode()


def test_auto_falls_back_to_html_on_emscripten(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "platform", "emscripten")
    monkeypatch.delitem(sys.modules, "marimo", raising=False)
    assert export.notebook_display_mode() == "html"


def test_marimo_keeps_widget_host_on_emscripten(monkeypatch: pytest.MonkeyPatch) -> None:
    # Marimo bundles its own anywidget frontend even in its WASM build, so an
    # Emscripten kernel with marimo imported still hosts the live widget.
    monkeypatch.setattr(sys, "platform", "emscripten")
    monkeypatch.setitem(sys.modules, "marimo", types.ModuleType("marimo"))
    assert export.notebook_display_mode() == "widget"


def test_environment_variable_overrides_emscripten_auto(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # A custom JupyterLite deployment that bundled the anywidget extension at
    # build time can force the widget host back on.
    monkeypatch.setattr(sys, "platform", "emscripten")
    monkeypatch.setenv("XY_NOTEBOOK_DISPLAY", "widget")
    assert export.notebook_display_mode() == "widget"


# -- show() and rich display --------------------------------------------------


def test_show_html_returns_isolated_iframe_view_without_widget() -> None:
    chart = _chart()
    view = chart.show(display="html")
    html = view._repr_html_()
    assert isinstance(view, export.HtmlView)
    assert html.startswith('<iframe class="xy-notebook-frame"')
    assert 'sandbox="allow-scripts"' in html
    assert str(view) == html
    assert chart._widget is None  # the html host never opens a widget comm


def test_show_auto_uses_html_host_on_emscripten(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "platform", "emscripten")
    monkeypatch.delitem(sys.modules, "marimo", raising=False)
    chart = _chart()
    view = chart.show()
    assert isinstance(view, export.HtmlView)
    assert chart._widget is None


def test_show_widget_override_wins_on_emscripten(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "platform", "emscripten")
    monkeypatch.setattr("xyg.widget.FigureWidget", _StubWidget)
    chart = _chart()
    assert chart.show(display="widget") is chart.widget()


def test_show_invalid_display_raises() -> None:
    with pytest.raises(ValueError, match="display must be one of"):
        _chart().show(display="standalone")


def test_ipython_display_uses_html_payload_on_emscripten(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import IPython.display

    displayed: list[tuple[object, bool]] = []

    def record(value: object, *, raw: bool = False) -> None:
        displayed.append((value, raw))

    monkeypatch.setattr(IPython.display, "display", record)
    monkeypatch.setattr(sys, "platform", "emscripten")
    monkeypatch.delitem(sys.modules, "marimo", raising=False)

    _chart()._ipython_display_()

    assert len(displayed) == 1
    payload, raw = displayed[0]
    assert raw is True
    assert isinstance(payload, dict)
    assert payload["text/html"].startswith('<iframe class="xy-notebook-frame"')


def test_ipython_display_keeps_widget_host_by_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import IPython.display

    displayed: list[object] = []
    monkeypatch.setattr(IPython.display, "display", lambda value, **kw: displayed.append(value))
    monkeypatch.setattr("xyg.widget.FigureWidget", _StubWidget)

    chart = _chart()
    chart._ipython_display_()

    assert displayed == [chart.widget()]


# -- notebook HTML export (anywidget / to_html shared client) -----------------


def test_scatter_to_html_includes_standalone_client() -> None:
    """Notebook / HTML export path inlines standalone.js + renderStandalone."""
    html = _chart().to_html()
    assert "var xy=" in html
    assert "renderStandalone" in html
    assert "MARK_KINDS" in html or "scatter" in html


def test_graph_to_html_includes_standalone_and_graph_meta() -> None:
    """graph_chart → figure → to_html carries graph meta for the shared client."""
    chart = xyg.graph_chart(
        xyg.graph(["a", "b", "c"], [("a", "b"), ("b", "c")], layout="grid"),
        width=400,
        height=300,
    )
    fig = chart.figure()
    assert fig._graph_meta is not None
    assert len(fig._graph_meta) == 1
    spec, blob = fig.build_payload()
    assert "graph" in spec
    assert isinstance(blob, (bytes, bytearray))
    html = chart.to_html()
    assert "var xy=" in html
    assert "renderStandalone" in html
    # Spec is JSON-inlined; graph meta must survive for CSR neighborhood hover.
    assert '"graph"' in html
    assert "csr_offsets" in html or "n_nodes" in html


def test_composition_api_graph_and_scatter_still_public() -> None:
    assert callable(xyg.graph_chart)
    assert callable(xyg.scatter_chart)
    assert callable(xyg.graph)
    assert callable(xyg.scatter)


def test_figure_show_honors_display_host() -> None:
    fig = _chart().figure()
    view = fig.show(display="html")
    assert isinstance(view, export.HtmlView)
    assert view._repr_html_().startswith('<iframe class="xy-notebook-frame"')


def test_facet_chart_show_honors_display_host() -> None:
    chart = xyg.facet_chart(
        xyg.line(x="x", y="y"),
        by="g",
        data={"x": [0.0, 1.0, 0.0, 1.0], "y": [1.0, 2.0, 3.0, 4.0], "g": ["a", "a", "b", "b"]},
    )
    view = chart.show(display="html")
    assert isinstance(view, export.HtmlView)
    assert view._repr_html_().startswith('<iframe class="xy-notebook-frame"')


def test_facet_chart_bare_display_is_composed_document_on_every_host(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # The one deliberate §3.3 exception: FacetChart's bare rich display always
    # emits the composed standalone-grid document (the only representation
    # that preserves the grid layout), which is WASM-safe as-is. Pin that it
    # stays the document on an Emscripten kernel; test_facets.py pins the
    # default-platform case.
    import IPython.display

    displayed: list[tuple[object, bool]] = []

    def record(value: object, *, raw: bool = False) -> None:
        displayed.append((value, raw))

    monkeypatch.setattr(IPython.display, "display", record)
    monkeypatch.setattr(sys, "platform", "emscripten")
    monkeypatch.delitem(sys.modules, "marimo", raising=False)

    xyg.facet_chart(
        xyg.line(x="x", y="y"),
        by="g",
        data={"x": [0.0, 1.0, 0.0, 1.0], "y": [1.0, 2.0, 3.0, 4.0], "g": ["a", "a", "b", "b"]},
    )._ipython_display_()

    assert len(displayed) == 1
    payload, raw = displayed[0]
    assert raw is True
    assert isinstance(payload, dict)
    assert payload["text/html"].startswith('<iframe class="xy-notebook-frame"')


def test_facet_grid_show_honors_display_host() -> None:
    grid = xyg.facet_chart(
        xyg.line(x="x", y="y"),
        by="g",
        data={"x": [0.0, 1.0, 0.0, 1.0], "y": [1.0, 2.0, 3.0, 4.0], "g": ["a", "a", "b", "b"]},
    ).figure()
    view = grid.show(display="html")
    assert isinstance(view, export.HtmlView)
    assert view._repr_html_().startswith('<iframe class="xy-notebook-frame"')
